"""
rag.py  —  Vectorless RAG backend
Chunking strategy: LLM-driven semantic chunking only.
  • Text is converted to markdown (heading heuristics for PDFs/TXT).
  • The LLM (Gemma E4B via LM Studio) decides which paragraphs belong together as a chunk.
  • There is NO fixed-size word-count chunking; the LLM owns all boundaries.
  • The only fallback (if the LLM call hard-fails) splits on blank lines (paragraph boundaries),
    which is still structure-aware, not size-aware.
"""

import html
import json
import os
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz
from docx import Document
from pydantic import BaseModel


# ── tuneable knobs ────────────────────────────────────────────────────────────
TOP_K = 4
# (CHUNK_SIZE / CHUNK_OVERLAP removed — LLM decides chunk boundaries)


# ── data model ────────────────────────────────────────────────────────────────
class TreeNode(BaseModel):
    id: str
    type: str
    text: str
    html: Optional[str] = None
    metadata: Dict[str, Any] = {}
    children: List["TreeNode"] = []

    class Config:
        arbitrary_types_allowed = True


TreeNode.update_forward_refs()


# ── text utilities ─────────────────────────────────────────────────────────────
def normalize_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    lines = [line.strip() for line in normalized.split("\n")]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def convert_text_to_markdown(text: str) -> str:
    """Add markdown headings for common document patterns (10-K ITEM headings etc.)."""
    if not text:
        return ""
    lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        if re.match(r"^ITEM\s+\d+[A-Za-z0-9\.]*", line, flags=re.I):
            lines.append(f"## {line}")
            continue
        if re.match(r"^[A-Z0-9][A-Z0-9\s\-\&\(\)]+$", line) and len(line.split()) <= 10:
            lines.append(f"## {line}")
            continue
        lines.append(line)
    markdown = "\n".join(lines)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


def save_markdown_export(filename: str, markdown_text: str) -> str:
    export_dir = Path.cwd() / "markdown_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    base_name = Path(filename).stem
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", base_name)
    output_file = export_dir / f"{safe_name}.md"
    if output_file.exists():
        output_file = export_dir / f"{safe_name}-{uuid.uuid4().hex[:8]}.md"
    output_file.write_text(markdown_text, encoding="utf-8")
    return str(output_file.relative_to(Path.cwd()))


def text_to_html(text: str) -> str:
    escaped = html.escape(text or "")
    lines = escaped.split("\n")
    paragraphs: List[str] = []
    buffer: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            continue
        if re.match(r"^(ITEM\s+\d+[A-Za-z0-9\.]*)[:\.]?", stripped, flags=re.I):
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            paragraphs.append(f"<strong>{stripped}</strong>")
            continue
        buffer.append(stripped)

    if buffer:
        paragraphs.append(" ".join(buffer))

    html_lines = []
    for paragraph in paragraphs:
        if paragraph.startswith("<strong>"):
            html_lines.append(f"<h3>{paragraph}</h3>")
        else:
            html_lines.append(f"<p>{paragraph}</p>")
    return "".join(html_lines) or "<pre class='whitespace-pre-wrap'>No preview available.</pre>"


# ── extraction ─────────────────────────────────────────────────────────────────
def extract_text_from_pdf(raw_bytes: bytes) -> str:
    with fitz.open(stream=raw_bytes, filetype="pdf") as doc:
        pages = [page.get_text("text") for page in doc]
    return "\n\n".join(pages)


def extract_text_from_docx(raw_bytes: bytes) -> str:
    with BytesIO(raw_bytes) as fp:
        document = Document(fp)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def extract_text_from_txt(raw_bytes: bytes) -> str:
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("latin-1")


def extract_document_text(filename: str, raw_bytes: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        text = extract_text_from_pdf(raw_bytes)
    elif extension in {".docx", ".doc"}:
        text = extract_text_from_docx(raw_bytes)
    elif extension in {".txt", ".md"}:
        text = extract_text_from_txt(raw_bytes)
    else:
        raise ValueError(f"Unsupported file type: {extension}")
    return normalize_text(text)


# ── LLM-driven chunking ────────────────────────────────────────────────────────
def llm_chunk_section(
    section_title: str,
    section_text: str,
    filename: str,
    model: str = "gemma-e4b",
) -> List[str]:
    """
    Ask the LLM to split a section's text into semantically coherent chunks.
    The LLM decides boundaries — NOT a word-count formula.
    Returns a list of chunk strings.
    """
    prompt = (
        "You are a document analyst. Split the following section text into semantically "
        "coherent chunks. Each chunk should cover one complete idea or topic. "
        "Group paragraphs that belong together into the same chunk. "
        "Do NOT split mid-argument. Do NOT create chunks smaller than one full paragraph. "
        "Return ONLY a JSON array of strings, where each string is one chunk. "
        "No extra keys, no markdown fences, no explanation.\n\n"
        f"Section title: {section_title}\n"
        f"Document: {filename}\n\n"
        f"Text:\n{section_text[:8000]}"
    )

    try:
        raw = generate_answer(prompt, model=model)
    except Exception:
        return _paragraph_fallback(section_text)

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(c, str) for c in parsed):
            return [c.strip() for c in parsed if c.strip()]
    except json.JSONDecodeError:
        pass

    # partial-parse attempt
    decoder = json.JSONDecoder()
    offset = 0
    raw = raw.lstrip()
    while offset < len(raw):
        try:
            obj, end = decoder.raw_decode(raw, offset)
        except json.JSONDecodeError:
            break
        if isinstance(obj, list):
            chunks = [str(c).strip() for c in obj if str(c).strip()]
            if chunks:
                return chunks
        offset = end
        while offset < len(raw) and raw[offset] in "\r\n \t":
            offset += 1

    return _paragraph_fallback(section_text)


def _paragraph_fallback(text: str) -> List[str]:
    """Structure-aware fallback: split on blank lines (paragraph boundaries only)."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    return paragraphs if paragraphs else [text]


# ── section extraction ─────────────────────────────────────────────────────────
def split_markdown_sections(markdown: str) -> List[Dict[str, str]]:
    """Rule-based: split on markdown headings."""
    sections: List[Dict[str, str]] = []
    current_title = None
    current_lines: List[str] = []

    for line in markdown.split("\n"):
        heading_match = re.match(r"^#{1,6}\s+(.*)$", line)
        if heading_match:
            if current_title is not None:
                sections.append({
                    "title": current_title,
                    "content": "\n".join(current_lines).strip(),
                })
            current_title = heading_match.group(1).strip()
            current_lines = []
            continue
        current_lines.append(line)

    if current_title is not None:
        sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
    elif current_lines:
        sections.append({"title": "Document", "content": "\n".join(current_lines).strip()})

    return sections


def extract_document_structure(
    filename: str, text: str, model: str = "gemma-e4b"
) -> List[Dict[str, str]]:
    """LLM-driven section extraction from free-form text."""
    structure_prompt = (
        "The input is markdown-like text. Parse it into a JSON array of sections using the document headings. "
        "Each section object must contain exactly two fields: title and content. "
        "Do not nest content under the wrong heading; every word must appear in exactly one section. "
        "Preserve original headings, especially 'ITEM' headings from a 10-K. "
        "Return only valid JSON with no extra explanation or formatting.\n\n"
        f"Document title: {filename}\n\nDocument text:\n{text[:12000]}"
    )

    try:
        response = generate_answer(structure_prompt, model=model)
    except Exception:
        return auto_extract_structure_from_text(text)

    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        parsed_objects: List[Any] = []
        decoder = json.JSONDecoder()
        offset = 0
        raw = response.lstrip()
        while offset < len(raw):
            try:
                obj, end = decoder.raw_decode(raw, offset)
            except json.JSONDecodeError:
                break
            if isinstance(obj, dict):
                parsed_objects.append(obj)
            offset = end
            while offset < len(raw) and raw[offset] in "\r\n \t":
                offset += 1
        parsed = parsed_objects[0] if parsed_objects else None

    if isinstance(parsed, dict) and "sections" in parsed and isinstance(parsed["sections"], list):
        return [
            {"title": str(s.get("title", "Untitled")).strip(), "content": str(s.get("content", "")).strip()}
            for s in parsed["sections"] if isinstance(s, dict)
        ]
    if isinstance(parsed, list):
        return [
            {"title": str(s.get("title", "Untitled")).strip(), "content": str(s.get("content", "")).strip()}
            for s in parsed if isinstance(s, dict)
        ]

    return auto_extract_structure_from_text(text)


def auto_extract_structure_from_text(text: str) -> List[Dict[str, str]]:
    pattern = re.compile(
        r"(ITEM\s+\d+[A-Za-z0-9\.]*[:\.]?\s*[^\n]+)\s*(.*?)"
        r"(?=ITEM\s+\d+[A-Za-z0-9\.]*[:\.]?\s*[^\n]+|\Z)",
        flags=re.I | re.S,
    )
    sections: List[Dict[str, str]] = []
    for match in pattern.finditer(text):
        title = match.group(1).strip()
        content = match.group(2).strip()
        if title and content:
            sections.append({"title": title, "content": content})
    return sections


# ── tree builder ───────────────────────────────────────────────────────────────
def build_document_tree(
    documents: List[Dict[str, Any]], model: str = "gemma-e4b"
) -> TreeNode:
    root_children: List[TreeNode] = []

    for document in documents:
        filename = document["filename"]
        raw_bytes = document["content"]

        text = extract_document_text(filename, raw_bytes)
        doc_id = str(uuid.uuid4())
        markdown_text = convert_text_to_markdown(text)

        # 1. Try heading-based section split first
        section_data = split_markdown_sections(markdown_text)

        # 2. If that produced nothing useful, ask the LLM to extract sections
        if not section_data or (len(section_data) == 1 and section_data[0]["title"] == "Document"):
            section_data = extract_document_structure(filename, markdown_text, model=model)

        section_nodes: List[TreeNode] = []

        for section_index, section in enumerate(section_data):
            section_title = section.get("title", "section")
            section_text = normalize_text(section.get("content", ""))
            section_html = text_to_html(section_text)

            # ── LLM decides chunk boundaries ──────────────────────────────
            chunk_texts = llm_chunk_section(
                section_title=section_title,
                section_text=section_text,
                filename=filename,
                model=model,
            )
            # ── (no word-count splitting) ──────────────────────────────────

            children: List[TreeNode] = []
            for chunk_index, chunk in enumerate(chunk_texts):
                children.append(
                    TreeNode(
                        id=f"{doc_id}-section-{section_index}-chunk-{chunk_index}",
                        type="chunk",
                        text=chunk,
                        html=text_to_html(chunk),
                        metadata={
                            "filename": filename,
                            "documentId": doc_id,
                            "sectionTitle": section_title,
                            "chunkingStrategy": "llm-semantic",
                        },
                    )
                )

            section_nodes.append(
                TreeNode(
                    id=f"{doc_id}-section-{section_index}",
                    type="section",
                    text="\n\n".join(child.text for child in children),
                    html=section_html,
                    metadata={
                        "filename": filename,
                        "documentId": doc_id,
                        "sectionTitle": section_title,
                    },
                    children=children,
                )
            )

        root_children.append(
            TreeNode(
                id=doc_id,
                type="document",
                text=text,
                html=text_to_html(text),
                metadata={"filename": filename},
                children=section_nodes,
            )
        )

    return TreeNode(
        id="root",
        type="root",
        text="Vectorless RAG document tree",
        children=root_children,
    )


# backward-compat alias
build_tree = build_document_tree


# ── tree utilities ─────────────────────────────────────────────────────────────
def serialize_tree(node: TreeNode) -> Dict[str, Any]:
    children = [child for child in node.children if child.type != "chunk"]
    return {
        "id": node.id,
        "type": node.type,
        "label": node.metadata.get("sectionTitle") or node.metadata.get("filename") or node.type,
        "summary": (node.text or "")[:180],
        "html": node.html,
        "metadata": node.metadata,
        "children": [serialize_tree(child) for child in children],
    }


def find_node_by_id(node: TreeNode, node_id: str) -> Optional[TreeNode]:
    if node.id == node_id:
        return node
    for child in node.children:
        found = find_node_by_id(child, node_id)
        if found:
            return found
    return None


def get_path_to_node(node: TreeNode, node_id: str) -> List[TreeNode]:
    if node.id == node_id:
        return [node]
    for child in node.children:
        path = get_path_to_node(child, node_id)
        if path:
            return [node] + path
    return []


def build_reasoning_trace(
    query: str, root: TreeNode, source_node_ids: List[str]
) -> List[str]:
    trace: List[str] = [f"Query: {query}"]
    if not source_node_ids:
        trace.append("No relevant nodes were identified.")
        return trace

    first_node = find_node_by_id(root, source_node_ids[0])
    if first_node is None:
        trace.append("Selected a search path but could not load node metadata.")
        return trace

    path = get_path_to_node(root, first_node.id)
    if len(path) > 1:
        doc_title = path[1].metadata.get("filename", "document")
        trace.append(f"Navigating to document: {doc_title}")
    if len(path) > 2:
        section_title = path[2].metadata.get("sectionTitle") or path[2].type
        trace.append(f"Exploring section: {section_title}")

    chunk_strategy = first_node.metadata.get("chunkingStrategy", "unknown")
    trace.append(f"Chunking strategy used: {chunk_strategy}")
    trace.append(f"Extracting content from node {first_node.id}.")
    trace.append(f"Chose {len(source_node_ids)} nodes along the reasoning path.")
    return trace


def compute_structural_score(
    query: str, root: TreeNode, source_node_ids: List[str]
) -> int:
    title_scores: List[int] = []
    query_terms = set(re.findall(r"\w+", query.lower()))

    for node_id in source_node_ids:
        node = find_node_by_id(root, node_id)
        if not node or node.type not in {"section", "document"}:
            continue
        title = str(node.metadata.get("sectionTitle") or node.metadata.get("filename") or "")
        title_terms = set(re.findall(r"\w+", title.lower()))
        title_scores.append(len(query_terms & title_terms))

    if not title_scores:
        return 40
    avg_match = sum(title_scores) / len(title_scores)
    return min(100, max(30, int(40 + avg_match * 15)))


def get_best_source_node(
    root: TreeNode, source_node_ids: List[str]
) -> Optional[TreeNode]:
    for node_id in source_node_ids:
        node = find_node_by_id(root, node_id)
        if node and node.type in {"section", "document"}:
            return node
    for node_id in source_node_ids:
        node = find_node_by_id(root, node_id)
        if node:
            return node
    return None


# ── retrieval ──────────────────────────────────────────────────────────────────
def score_text(query: str, text: str) -> int:
    query_terms = set(re.findall(r"\w+", query.lower()))
    text_terms = set(re.findall(r"\w+", text.lower()))
    return len(query_terms & text_terms)


def retrieve_tree(
    query: str, root: TreeNode, top_k: int = TOP_K
) -> Tuple[List[Tuple[str, str]], List[str]]:
    scored_docs = [(score_text(query, doc.text), doc) for doc in root.children]
    scored_docs.sort(key=lambda item: (-item[0], item[1].id))
    top_docs = [doc for score, doc in scored_docs if score > 0][:top_k]
    if not top_docs:
        top_docs = [doc for _, doc in scored_docs[:top_k]]

    chunks: List[Tuple[str, str]] = []
    source_ids: List[str] = []

    for doc in top_docs:
        source_ids.append(doc.id)
        scored_sections = [(score_text(query, section.text), section) for section in doc.children]
        scored_sections.sort(key=lambda item: (-item[0], item[1].id))
        top_sections = [section for score, section in scored_sections if score > 0][:top_k]
        if not top_sections:
            top_sections = [section for _, section in scored_sections[:top_k]]

        for section in top_sections:
            source_ids.append(section.id)
            scored_chunks = [(score_text(query, chunk.text), chunk) for chunk in section.children]
            scored_chunks.sort(key=lambda item: (-item[0], item[1].id))
            top_chunks = [chunk for score, chunk in scored_chunks if score > 0][:top_k]
            if not top_chunks:
                top_chunks = [chunk for _, chunk in scored_chunks[:top_k]]

            for chunk in top_chunks:
                chunks.append((chunk.id, chunk.text))
                source_ids.append(chunk.id)

    unique_ids: List[str] = []
    for node_id in source_ids:
        if node_id not in unique_ids:
            unique_ids.append(node_id)

    return chunks[:top_k], unique_ids


# ── prompt & answer generation ────────────────────────────────────────────────
def build_prompt(query: str, chunks: List[Tuple[str, str]]) -> str:
    prompt_blocks: List[str] = []
    for index, (chunk_id, text) in enumerate(chunks, start=1):
        snippet = text.strip()
        if len(snippet) > 500:
            snippet = snippet[:500].rstrip() + "..."
        prompt_blocks.append(f"Chunk {index} (id: {chunk_id}):\n{snippet}")
    context = "\n\n---\n\n".join(prompt_blocks)
    return (
        "You are a precise assistant. Use ONLY the provided context to answer the question. "
        "Do not invent facts or use information outside the context. "
        "If the answer is not in the context, reply exactly: I don't know.\n\n"
        "Cite any relevant chunk ids from the provided context in your answer.\n\n"
        f"Context:\n{context}\n\nQuestion:\n{query}\n\nAnswer:"
    )


def generate_answer(prompt: str, model: str = "gemma-e4b") -> str:
    """Call the local LM Studio server (OpenAI-compatible API) to generate an answer."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore
    if load_dotenv is not None:
        load_dotenv()

    import socket
    from urllib import error, request as urllib_request

    api_url = os.environ.get("LLM_API_URL", "http://127.0.0.1:1234")
    api_key = os.environ.get("LLM_API_KEY", "lm-studio")
    timeout_seconds = int(os.environ.get("LLM_TIMEOUT", "120"))

    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 512,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a concise and precise document assistant. "
                    "Only answer from the provided context. "
                    "If the context does not contain the answer, reply exactly: I don't know."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    body = json.dumps(payload).encode("utf-8")
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request_obj = urllib_request.Request(
        f"{api_url.rstrip('/')}/v1/chat/completions",
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib_request.urlopen(request_obj, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        payload_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API error {exc.code}: {payload_text}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"LLM API request failed: {exc}") from exc
    except socket.timeout as exc:
        raise RuntimeError(
            f"LLM API request timed out after {timeout_seconds}s. "
            "Check that LM Studio is running, or increase LLM_TIMEOUT."
        ) from exc

    try:
        response_json = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response from LLM API: {raw[:200]}") from exc

    def _strip_think_tags(text: str) -> str:
        """Remove <think>...</think> blocks; if content follows, return that. Otherwise return text as-is."""
        # Split on closing tag; anything after </think> is the final answer
        parts = re.split(r"</think>", text, flags=re.IGNORECASE)
        if len(parts) > 1:
            after = parts[-1].strip()
            if after:
                return after
        # Also remove any unclosed leading <think> block if the whole text is wrapped in it
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        if cleaned:
            return cleaned
        return text.strip()

    # OpenAI-compatible response parsing with LM Studio tolerance.
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = choices[0]

        # Non-streaming: choices[0].message.content
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return _strip_think_tags(content.strip())
            if isinstance(content, list):
                parts: List[str] = []
                for item in content:
                    if isinstance(item, str):
                        if item.strip():
                            parts.append(item.strip())
                    elif isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
                if parts:
                    return _strip_think_tags("\n".join(parts))

            # reasoning_content is the internal chain-of-thought, NOT the final answer.
            # Some thinking models (DeepSeek-R1, QwQ) set content=null and put thinking here.
            # Try to extract the final answer after a </think> marker; fall back to the last
            # paragraph only if there is a clear structural break.
            reasoning_raw = message.get("reasoning_content")
            if isinstance(reasoning_raw, str) and reasoning_raw.strip():
                extracted = _strip_think_tags(reasoning_raw.strip())
                # If stripping produced something shorter, we found a clean answer section.
                if extracted != reasoning_raw.strip():
                    return extracted
                # No </think> delimiter — take the last non-empty paragraph as the answer.
                paragraphs = [p.strip() for p in re.split(r"\n{2,}", reasoning_raw.strip()) if p.strip()]
                if paragraphs:
                    return paragraphs[-1]

        # Streaming-like variant: choices[0].delta.content
        delta = choice.get("delta")
        if isinstance(delta, dict):
            delta_content = delta.get("content")
            if isinstance(delta_content, str) and delta_content.strip():
                return delta_content.strip()

        # Legacy/alternate variant: choices[0].text
        text = choice.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    # Some local servers return a direct response/content field.
    fallback_response = response_json.get("response")
    if isinstance(fallback_response, str) and fallback_response.strip():
        return fallback_response.strip()
    fallback_content = response_json.get("content")
    if isinstance(fallback_content, str) and fallback_content.strip():
        return fallback_content.strip()

    raise RuntimeError(
        "Unexpected LLM API response format. "
        f"Top-level keys: {sorted(list(response_json.keys()))}"
    )


# ── query entrypoint ───────────────────────────────────────────────────────────
def query_tree(
    query: str, root: TreeNode, model: str = "gemma-e4b"
) -> Tuple[str, List[str], List[str], int, str, str, str]:
    top_chunks, source_node_ids = retrieve_tree(query, root)

    if not top_chunks:
        return (
            "I don't know.",
            [],
            ["No context was retrieved from the document tree."],
            0, "", "", "",
        )

    prompt = build_prompt(query, top_chunks)
    answer = generate_answer(prompt, model=model)
    reasoning = build_reasoning_trace(query, root, source_node_ids)
    confidence = compute_structural_score(query, root, source_node_ids)
    source_node = get_best_source_node(root, source_node_ids)
    source_html = (
        source_node.html if source_node and source_node.html
        else text_to_html(source_node.text if source_node else "")
    )
    source_title = (
        source_node.metadata.get("sectionTitle")
        or source_node.metadata.get("filename")
        or "Source"
    ) if source_node else ""
    source_node_id = source_node.id if source_node else ""

    return answer, source_node_ids, reasoning, confidence, source_html, source_node_id, source_title


# ── react-flow serialisation ───────────────────────────────────────────────────
def format_node_label(node: TreeNode) -> str:
    if node.type == "root":
        return "root"
    if node.type == "document":
        return f"document: {node.metadata.get('filename', 'unknown')}"
    text = node.text.replace("\n", " ").strip()
    snippet = text[:80].strip()
    if len(text) > 80:
        snippet += "..."
    return f"{node.type}: {snippet}"


def flatten_tree_to_react_flow(root: TreeNode) -> Dict[str, List[Dict[str, Any]]]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    def walk(node: TreeNode, parent_id: Optional[str] = None) -> None:
        nodes.append({
            "id": node.id,
            "type": "default",
            "data": {
                "label": format_node_label(node),
                "text": node.text,
                "html": node.html,
                "metadata": node.metadata,
                "nodeType": node.type,
            },
            "position": {"x": 0, "y": 0},
        })
        if parent_id is not None:
            edges.append({
                "id": f"e-{parent_id}-{node.id}",
                "source": parent_id,
                "target": node.id,
            })
        for child in node.children:
            walk(child, node.id)

    walk(root)
    return {"nodes": nodes, "edges": edges}
