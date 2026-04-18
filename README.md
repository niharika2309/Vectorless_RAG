# Vectorless RAG

A document reasoning system that answers questions over uploaded files **without a vector database**. Instead of embedding-based similarity search, it uses an LLM to semantically chunk documents into a hierarchical tree and navigates that tree structurally to retrieve and answer.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Streamlit UI (port 8501)                      │
│                                                                       │
│   ┌──────────────────────────┐   ┌─────────────────────────────────┐ │
│   │   Left Panel             │   │   Right Panel                   │ │
│   │   ─────────────────────  │   │   ──────────────────────────    │ │
│   │   • File uploader        │   │   • Chat history (bubbles)      │ │
│   │   • "Process" button     │   │   • Per-message answer          │ │
│   │   • Document Graph       │   │   • Confidence badge            │ │
│   │     (Graphviz/SVG)       │   │   • Source node label           │ │
│   │     hover → chunk text   │   │   • Collapsable Reasoning       │ │
│   └──────────┬───────────────┘   └──────────────┬──────────────────┘ │
└──────────────┼──────────────────────────────────┼────────────────────┘
               │  POST /upload (multipart)         │  POST /query (JSON)
               ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend  (port 8000)                     │
│                            main.py                                   │
│                                                                       │
│   /upload ──► extract text ──► build_document_tree()                 │
│               └─ returns: sessionId, reactFlow, documentTree         │
│                                                                       │
│   /query  ──► look up session ──► query_tree()                       │
│               └─ returns: answer, reasoning, confidence,             │
│                           sourceNodeId, sourceTitle, sourceHtml      │
│                                                                       │
│   Session store: app.state.sessions  (in-memory, per-process)        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        rag.py  —  Core Pipeline                      │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  INGESTION                                                    │    │
│  │                                                               │    │
│  │  Raw file bytes                                               │    │
│  │      │                                                        │    │
│  │      ▼                                                        │    │
│  │  extract_document_text()  (PyMuPDF / python-docx / plain)    │    │
│  │      │                                                        │    │
│  │      ▼                                                        │    │
│  │  convert_text_to_markdown()  (heading heuristics)            │    │
│  │      │                                                        │    │
│  │      ▼                                                        │    │
│  │  split_markdown_sections()  ── rule-based heading split       │    │
│  │      │  if no headings found:                                 │    │
│  │      └──► extract_document_structure()  ── LLM section parse │    │
│  │                                                               │    │
│  │      ▼  (for each section)                                    │    │
│  │  llm_chunk_section()  ── LLM decides semantic chunk borders   │    │
│  │      └── fallback: _paragraph_fallback() on blank lines       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  TREE STRUCTURE (in-memory, no vector DB)                     │    │
│  │                                                               │    │
│  │   Root                                                        │    │
│  │   └── Document  (one per uploaded file)                       │    │
│  │       └── Section  (heading-level splits)                     │    │
│  │           └── Chunk  (LLM-defined semantic units)             │    │
│  │                                                               │    │
│  │  Serialised as reactFlow {nodes, edges} for graph display     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  RETRIEVAL  (no embeddings — structural keyword scoring)      │    │
│  │                                                               │    │
│  │  retrieve_tree(query, root)                                   │    │
│  │      └── walks every chunk, scores by term overlap            │    │
│  │          returns top-K=4 chunks + their node IDs              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ANSWER GENERATION                                            │    │
│  │                                                               │    │
│  │  build_prompt(query, top_chunks)                              │    │
│  │      │                                                        │    │
│  │      ▼                                                        │    │
│  │  generate_answer()  ──► LM Studio (OpenAI-compatible API)     │    │
│  │                         model: gemma-e4b                      │    │
│  │      │                                                        │    │
│  │      ▼                                                        │    │
│  │  build_reasoning_trace()  — structural navigation log         │    │
│  │  compute_structural_score() — confidence (0–100)              │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  OpenAI-compatible HTTP
                           ▼
              ┌────────────────────────┐
              │   LM Studio            │
              │   gemma-e4b            │
              │   http://127.0.0.1:1234│
              └────────────────────────┘
```

### Key design decisions

| Concern | Decision |
|---|---|
| Chunking | LLM-driven semantic boundaries — no fixed token window |
| Retrieval | Keyword term-overlap scoring over the tree — no embeddings, no vector DB |
| Section detection | Markdown heading heuristics first; LLM fallback for unstructured text |
| State | In-memory session map in FastAPI (`app.state.sessions`) — stateless across restarts |
| Visualisation | Graphviz DOT rendered as SVG; node tooltips show raw chunk text on hover |

---

## What this project does

- Accepts PDF, DOCX, and TXT uploads.
- Converts documents into plain text and uses Gemma E4B (via LM Studio) to extract section structure when headings are absent.
- Builds a hierarchical tree: `Root → Document → Section → Chunk`.
- Retrieves the most relevant chunks by structural keyword scoring (no vectors).
- Generates a grounded answer with a reasoning trace and confidence score.
- Visualises the document tree as an interactive graph — hover a node to preview its text.

---

## Repository files

| File | Purpose |
|---|---|
| `main.py` | FastAPI server — `/upload` and `/query` endpoints |
| `rag.py` | Document ingestion, tree builder, retrieval, LM Studio integration |
| `streamlit_app.py` | Streamlit UI — two-column layout (graph + chat) |
| `requirements.txt` | Python dependencies |
| `run_bash.sh` | One-command launcher for backend + Streamlit |
| `.env.example` | Optional LM Studio URL / key overrides |
| `.streamlit/config.toml` | Light blue Streamlit theme |

---

## Run the app

### Prerequisites

- Python 3.9+
- [LM Studio](https://lmstudio.ai/) with **Gemma E4B** loaded and the local server running on `http://127.0.0.1:1234`

### 1. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Also install Streamlit (system-level, outside venv)
pip3 install streamlit
```

### 2. Start everything

```bash
bash run_bash.sh
```

This launches the FastAPI backend on `http://127.0.0.1:8000` and the Streamlit UI on `http://127.0.0.1:8501`. Both are stopped cleanly on Ctrl+C.

### 3. Manual start (optional)

```bash
# Terminal 1 — backend
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend
streamlit run streamlit_app.py --server.port 8501
```

---

## Configuration

Create a `.env` file in the project root to override LM Studio defaults:

```env
LLM_API_URL=http://127.0.0.1:1234
# LLM_API_KEY=lm-studio
# LLM_TIMEOUT=120
```

---

## How a query flows end-to-end

1. User uploads a file → Streamlit POSTs bytes to `/upload`.
2. Backend extracts text, converts to Markdown, splits into sections (rule-based → LLM fallback).
3. LLM (Gemma E4B) assigns semantic chunk boundaries inside each section.
4. A `Root → Document → Section → Chunk` tree is built and stored in the session.
5. The tree is serialised as a Graphviz graph and returned to the UI for display.
6. User types a question → Streamlit POSTs to `/query`.
7. Backend walks every leaf chunk, scores by term overlap, keeps top-4.
8. Selected chunks are assembled into a prompt and sent to LM Studio.
9. The answer, reasoning trace, and confidence are returned and rendered in the chat panel.
