# Vectorless RAG

Vectorless RAG is a retrieval-augmented generation approach that avoids a dedicated vector database or embedding index. Instead, it relies on local document structure, text chunking, and simple relevance scoring to retrieve supporting content before generation.

The key idea is to keep the pipeline lightweight and transparent: documents are parsed, broken into sections and chunks, and ranked by keyword overlap with the query. The model is then asked to generate an answer using only the retrieved context.

## What this project does

- Accepts PDF, DOCX, and TXT uploads.
- Converts documents into plain text and uses Gemma4 to extract section structure when available.
- Builds a hierarchical tree: `Root → Document → Section → Chunk`.
- Flattens the tree into a React Flow graph for visualization.
- Stores the parsed tree in session memory so queries reuse the upload state.
- Retrieves the most relevant chunks for a question and generates a grounded answer with `gemma4:latest`.

## Architecture

### Backend

- `main.py` — FastAPI server with `/upload` and `/query` endpoints.
- `rag.py` — document ingestion, chunking, retrieval, tree building, and Ollama integration.
- Uploads are stored in a session object in `app.state.sessions`.
- The backend returns `sourceNodeIds` so the frontend can highlight the retrieval path.

### Frontend

- `frontend/` — Next.js App Router app with TypeScript and Tailwind CSS.
- Visualizes the document tree using React Flow.
- Uploads files and queries the backend from the browser.

## Run the app

### Backend

```bash
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open:

```bash
http://localhost:3000
```

## Configuration

This repo includes `.env.example` for optional Ollama settings.

Create a `.env` file if you need a custom Ollama host:

```env
OLLAMA_API_URL=http://127.0.0.1:11434
# OLLAMA_API_KEY=your_api_key
```

If Ollama is running locally on the default URL, no `.env` file is required.

## How it works

1. User uploads PDF/DOCX/TXT files through the frontend.
2. Backend extracts the text and uses Gemma4 to identify document sections where possible.
3. The backend builds a hierarchical tree and returns a React Flow graph.
4. The frontend renders the tree and displays upload status.
5. User submits a question against the current session.
6. Backend retrieves the most relevant chunks and sends them to Ollama.
7. Ollama returns a grounded answer, and the frontend highlights the source node ids.

## Notes

- The tree is generated locally by the backend, not by the model.
- The model is used only for structure extraction and answer generation.
- `gemma4:latest` is the default model in this repo.

## Repository files

- `main.py` — FastAPI backend entrypoint.
- `rag.py` — document ingestion, tree builder, retrieval, and Ollama integration.
- `requirements.txt` — Python backend dependencies.
- `frontend/` — React/Next.js frontend and visualization UI.
- `.env.example` — optional Ollama configuration.
- `tests/` — backend test scaffolding.
