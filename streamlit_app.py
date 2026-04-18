import html as html_lib
import requests
import streamlit as st

BACKEND_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Vectorless RAG",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ───────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .stApp { background-color: #e8f4fd; }
    [data-testid="stSidebar"] { display: none; }
    h1 { color: #0d47a1 !important; font-size: 1.5rem !important; margin-bottom: 0 !important; }
    h3 { color: #1565c0 !important; font-size: 1rem !important; margin: 0.5rem 0 0.4rem 0 !important; }
    hr { border-color: #90caf9; margin: 0.6rem 0; }
    .stButton > button {
        background-color: #1976d2; color: white;
        border: none; border-radius: 8px;
        padding: 0.4rem 1.1rem; font-weight: 600;
        transition: background 0.2s; width: 100%;
    }
    .stButton > button:hover { background-color: #1565c0; }
    .stButton > button:disabled { background-color: #90caf9; }
    [data-testid="stFileUploader"] {
        background-color: #dbeafe;
        border: 2px dashed #42a5f5;
        border-radius: 10px; padding: 0.5rem;
    }
    .msg-user { display: flex; justify-content: flex-end; margin: 0.45rem 0; }
    .bubble-user {
        background: #1976d2; color: white;
        border-radius: 16px 16px 4px 16px;
        padding: 0.55rem 0.9rem; max-width: 80%;
        font-size: 0.92rem; line-height: 1.45;
    }
    .msg-bot { display: flex; justify-content: flex-start; margin: 0.45rem 0; }
    .bubble-bot {
        background: #ffffff; color: #0d47a1;
        border: 1px solid #bbdefb;
        border-radius: 16px 16px 16px 4px;
        padding: 0.55rem 0.9rem; max-width: 80%;
        font-size: 0.92rem; line-height: 1.45;
    }
    .conf-badge {
        display: inline-block;
        background: #bbdefb; color: #0d47a1;
        border-radius: 10px; padding: 0.1rem 0.6rem;
        font-size: 0.75rem; font-weight: 600; margin-top: 0.3rem;
    }
    .source-tag { font-size: 0.75rem; color: #5c8abf; margin-top: 0.25rem; }
    [data-testid="stExpander"] summary {
        color: #1565c0; font-size: 0.8rem; font-weight: 600; padding: 0;
    }
    .reasoning-step {
        background: #e3f2fd;
        border-left: 3px solid #64b5f6;
        border-radius: 4px;
        padding: 0.45rem 0.7rem; margin: 0.3rem 0;
        font-size: 0.82rem; color: #1565c0;
    }
    [data-testid="stForm"] { background: transparent !important; border: none !important; }
    .stTextInput > div > input {
        border: 1.5px solid #90caf9; border-radius: 8px;
        background-color: #f0f9ff; font-size: 0.92rem;
    }
    .stTextInput > div > input:focus {
        border-color: #1976d2; box-shadow: 0 0 0 2px #bbdefb;
    }
    .empty-state { color: #90b4d4; font-size: 0.88rem; text-align: center; margin-top: 2rem; }
    [data-testid="stHorizontalBlock"] > div:first-child { padding-right: 0.75rem; }
    [data-testid="stHorizontalBlock"] > div:last-child  { padding-left:  0.75rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def build_dot_graph(react_flow: dict) -> str:
    """Graphviz DOT — tooltip carries chunk text shown on SVG node hover."""
    lines = [
        "digraph G {",
        "  rankdir=TB;",
        '  bgcolor="#f0f8ff";',
        '  node [style=filled, fillcolor="#bbdefb", color="#1565c0",'
        '        fontcolor="#0d47a1", fontname="Arial", fontsize=10];',
        '  edge [color="#42a5f5", arrowsize=0.7];',
    ]
    for node in react_flow.get("nodes", []):
        data = node.get("data", {})
        label = data.get("label", node.get("id", ""))
        if len(label) > 35:
            label = label[:32] + "\u2026"
        text = (data.get("text") or "")[:400]
        tooltip = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        label_esc = label.replace('"', '\\"').replace("\n", "\\n")
        nid = node["id"].replace('"', '\\"')
        lines.append(f'  "{nid}" [label="{label_esc}", tooltip="{tooltip}"];')
    for edge in react_flow.get("edges", []):
        src = edge["source"].replace('"', '\\"')
        tgt = edge["target"].replace('"', '\\"')
        lines.append(f'  "{src}" -> "{tgt}";')
    lines.append("}")
    return "\n".join(lines)


def upload_files(files) -> dict:
    tuples = [("files", (f.name, f.getvalue(), f.type or "application/octet-stream")) for f in files]
    resp = requests.post(f"{BACKEND_URL}/upload", files=tuples, timeout=120)
    resp.raise_for_status()
    return resp.json()


def query_backend(session_id: str, question: str) -> dict:
    resp = requests.post(
        f"{BACKEND_URL}/query",
        json={"sessionId": session_id, "query": question},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def render_chat_history(history: list) -> None:
    for entry in history:
        q_esc = html_lib.escape(entry["question"])
        st.markdown(
            f'<div class="msg-user"><div class="bubble-user">{q_esc}</div></div>',
            unsafe_allow_html=True,
        )
        answer_esc = html_lib.escape(entry["answer"])
        conf = entry.get("confidence", 0)
        source = html_lib.escape(entry.get("source_title", ""))
        source_line = f'<div class="source-tag">&#128204; {source}</div>' if source else ""
        st.markdown(
            f'<div class="msg-bot"><div class="bubble-bot">'
            f'{answer_esc}'
            f'<div class="conf-badge">Confidence: {conf}%</div>'
            f'{source_line}'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        reasoning = entry.get("reasoning", [])
        if reasoning:
            with st.expander("\U0001f9e0 Reasoning", expanded=False):
                for step in reasoning:
                    step_esc = html_lib.escape(step)
                    st.markdown(
                        f'<div class="reasoning-step">{step_esc}</div>',
                        unsafe_allow_html=True,
                    )


# ── State init ────────────────────────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="padding:0.25rem 0 0.1rem 0">\U0001f50d Vectorless RAG</h1>'
    '<p style="color:#5c8abf;font-size:0.82rem;margin:0 0 0.5rem 0">'
    'Upload a document \u2014 ask anything, no vector database needed.</p>',
    unsafe_allow_html=True,
)
st.divider()

# ── Two-column layout ─────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ═══════════════ LEFT ─ upload + graph ═══════════════════════════════════════
with left:
    st.markdown('<h3>&#128196; Document</h3>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "PDF, DOCX, or TXT",
        accept_multiple_files=True,
        type=["pdf", "docx", "txt"],
        label_visibility="collapsed",
    )

    process_clicked = st.button("Process document", disabled=not uploaded)

    if process_clicked and uploaded:
        with st.spinner("Building document graph\u2026"):
            try:
                result = upload_files(uploaded)
                st.session_state["session_id"] = result["sessionId"]
                st.session_state["react_flow"] = result["reactFlow"]
                st.session_state["doc_count"] = result["documentCount"]
                st.session_state["chat_history"] = []
            except requests.HTTPError as e:
                st.error(f"Upload failed: {e.response.text}")
            except Exception as e:
                st.error(f"Upload failed: {e}")

    if "session_id" in st.session_state:
        st.success(f"\u2705 {st.session_state['doc_count']} document(s) ready")

    st.divider()
    st.markdown('<h3>&#128202; Document Graph</h3>', unsafe_allow_html=True)
    st.caption("Hover over a node to preview its chunk text.")

    if "react_flow" not in st.session_state:
        st.markdown(
            '<p class="empty-state">Process a document to see the graph.</p>',
            unsafe_allow_html=True,
        )
    else:
        rf = st.session_state["react_flow"]
        n = len(rf.get("nodes", []))
        e = len(rf.get("edges", []))
        st.caption(f"{n} nodes \u00b7 {e} edges")
        st.graphviz_chart(build_dot_graph(rf), use_container_width=True)

# ═══════════════ RIGHT ─ chat ════════════════════════════════════════════════
with right:
    st.markdown('<h3>&#128172; Chat</h3>', unsafe_allow_html=True)

    if "session_id" not in st.session_state:
        st.markdown(
            '<p class="empty-state">Process a document on the left to start chatting.</p>',
            unsafe_allow_html=True,
        )
    else:
        if st.session_state["chat_history"]:
            render_chat_history(st.session_state["chat_history"])
        else:
            st.markdown(
                '<p class="empty-state">Ask your first question below.</p>',
                unsafe_allow_html=True,
            )

        st.divider()

        with st.form("chat_form", clear_on_submit=True):
            cols = st.columns([5, 1])
            with cols[0]:
                question = st.text_input(
                    "q",
                    placeholder="Ask something about the document\u2026",
                    label_visibility="collapsed",
                )
            with cols[1]:
                send = st.form_submit_button("Send", use_container_width=True)

        if send and question.strip():
            with st.spinner(""):
                try:
                    ans = query_backend(st.session_state["session_id"], question.strip())
                    st.session_state["chat_history"].append({
                        "question": question.strip(),
                        "answer": ans.get("answer", ""),
                        "reasoning": ans.get("reasoning", []),
                        "confidence": ans.get("confidence", 0),
                        "source_title": ans.get("sourceTitle", ""),
                    })
                    st.rerun()
                except requests.HTTPError as e:
                    st.error(f"Query failed: {e.response.text}")
                except Exception as e:
                    st.error(f"Query failed: {e}")
