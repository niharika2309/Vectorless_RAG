import json
import os
import re
import uuid
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from pydantic import BaseModel
from pdfminer.high_level import extract_text_to_fp

CHUNK_SIZE = 220
CHUNK_OVERLAP = 40
SECTION_SIZE = 4
TOP_K = 4


class TreeNode(BaseModel):
    id: str
    type: str
    text: str
    metadata: Dict[str, Any] = {}
    children: List["TreeNode"] = []

    class Config:
        arbitrary_types_allowed = True


TreeNode.update_forward_refs()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_text_from_pdf(raw_bytes: bytes) -> str:
    output = StringIO()
    with BytesIO(raw_bytes) as fp:
        extract_text_to_fp(fp, output)
    return output.getvalue()


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


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    words = re.findall(r"\S+", text)
    chunks: List[str] = []
    start = 0

    while start < len(words):
        chunk = " ".join(words[start : start + chunk_size])
        if chunk:
            chunks.append(chunk)
        start += max(chunk_size - overlap, 1)

    return chunks


def build_document_tree(documents: List[Dict[str, Any]]) -> TreeNode:
    root_children: List[TreeNode] = []

    for document in documents:
        filename = document["filename"]
        raw_bytes = document["content"]
        text = extract_document_text(filename, raw_bytes)
        doc_id = str(uuid.uuid4())

        section_data = extract_document_structure(filename, text)
        section_nodes: List[TreeNode] = []

        if section_data:
            for section_index, section in enumerate(section_data):
                children = []
                section_text = normalize_text(section.get("content", ""))
                for chunk_index, chunk in enumerate(chunk_text(section_text)):
                    children.append(
                        TreeNode(
                            id=f"{doc_id}-section-{section_index}-chunk-{chunk_index}",
                            type="chunk",
                            text=chunk,
                            metadata={
                                "filename": filename,
                                "documentId": doc_id,
                                "sectionTitle": section.get("title", "section"),
                            },
                        )
                    )

                section_nodes.append(
                    TreeNode(
                        id=f"{doc_id}-section-{section_index}",
                        type="section",
                        text="\n\n".join(child.text for child in children),
                        metadata={
                            "filename": filename,
                            "documentId": doc_id,
                            "sectionTitle": section.get("title", "section"),
                        },
                        children=children,
                    )
                )
        else:
            chunk_nodes: List[TreeNode] = []
            for index, chunk in enumerate(chunk_text(text)):
                chunk_nodes.append(
                    TreeNode(
                        id=f"{doc_id}-chunk-{index}",
                        type="chunk",
                        text=chunk,
                        metadata={"filename": filename, "documentId": doc_id},
                    )
                )

            for section_index in range(0, len(chunk_nodes), SECTION_SIZE):
                children = chunk_nodes[section_index : section_index + SECTION_SIZE]
                section_nodes.append(
                    TreeNode(
                        id=f"{doc_id}-section-{section_index // SECTION_SIZE}",
                        type="section",
                        text="\n\n".join(child.text for child in children),
                        metadata={"filename": filename, "documentId": doc_id},
                        children=children,
                    )
                )

        root_children.append(
            TreeNode(
                id=doc_id,
                type="document",
                text=text,
                metadata={"filename": filename},
                children=section_nodes,
            )
        )

    return TreeNode(id="root", type="root", text="Vectorless RAG document tree", children=root_children)


# Backward compatibility for legacy imports.
build_tree = build_document_tree


def score_text(query: str, text: str) -> int:
    query_terms = set(re.findall(r"\w+", query.lower()))
    text_terms = set(re.findall(r"\w+", text.lower()))
    return len(query_terms & text_terms)


def retrieve_tree(query: str, root: TreeNode, top_k: int = TOP_K) -> Tuple[List[Tuple[str, str]], List[str]]:
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


def extract_document_structure(filename: str, text: str, model: str = "gemma4:latest") -> List[Dict[str, str]]:
    structure_prompt = (
        "Parse the document into a JSON array of sections. "
        "Each section object must contain a title and content. "
        "Return only valid JSON, with no extra explanation. "
        "Use the document title when possible.\n\n"
        f"Document title: {filename}\n\n"
        f"Document text:\n{text[:12000]}"
    )
    response = generate_answer_ollama(structure_prompt, model=model)

    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        parsed_objects = []
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
            {
                "title": str(section.get("title", "Untitled section")).strip(),
                "content": str(section.get("content", "")).strip(),
            }
            for section in parsed["sections"]
            if isinstance(section, dict)
        ]

    if isinstance(parsed, list):
        return [
            {
                "title": str(section.get("title", "Untitled section")).strip(),
                "content": str(section.get("content", "")).strip(),
            }
            for section in parsed
            if isinstance(section, dict)
        ]

    return []


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
        "Do not invent facts or use information outside the context. If the answer is not in the context, reply exactly: I don't know.\n\n"
        "Cite any relevant chunk ids from the provided context in your answer.\n\n"
        f"Context:\n{context}\n\nQuestion:\n{query}\n\nAnswer:"
    )


def generate_answer_ollama(prompt: str, model: str = "gemma4:latest") -> str:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    if load_dotenv is not None:
        load_dotenv()

    from urllib import error, request
    import json

    api_url = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434")
    api_key = os.environ.get("OLLAMA_API_KEY")

    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 512,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a concise and precise document assistant. Only answer from the provided context. "
                    "If the context does not contain the answer, reply exactly: I don't know."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request_obj = request.Request(
        f"{api_url.rstrip('/')}/api/chat",
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with request.urlopen(request_obj, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama error {exc.code}: {payload}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc

    def parse_json_objects(text: str) -> List[Dict[str, Any]]:
        objects: List[Dict[str, Any]] = []
        decoder = json.JSONDecoder()
        offset = 0
        text = text.lstrip()
        while offset < len(text):
            try:
                obj, end = decoder.raw_decode(text, offset)
            except json.JSONDecodeError:
                break
            if isinstance(obj, dict):
                objects.append(obj)
            offset = end
            while offset < len(text) and text[offset] in "\r\n \t":
                offset += 1
        return objects

    objects: List[Dict[str, Any]]
    try:
        response_json = json.loads(raw)
        objects = [response_json] if isinstance(response_json, dict) else []
    except json.JSONDecodeError:
        objects = parse_json_objects(raw)

    assistant_parts: List[str] = []
    for obj in objects:
        if isinstance(obj.get("message"), dict):
            message = obj["message"]
            content = message.get("content")
            if isinstance(content, str) and content:
                assistant_parts.append(content)
        elif "response" in obj:
            assistant_parts.append(str(obj["response"]))
        elif "output" in obj:
            output = obj["output"]
            if isinstance(output, list) and output:
                assistant_parts.append(str(output[0]))
        elif "text" in obj and isinstance(obj["text"], str):
            assistant_parts.append(obj["text"])

    answer = "".join(assistant_parts).strip()
    if answer:
        return answer

    if objects:
        last = objects[-1]
        if isinstance(last.get("message"), dict):
            return str(last["message"].get("content", "")).strip()

    raise RuntimeError(f"Unexpected Ollama response format: {objects}")


def query_tree(query: str, root: TreeNode, model: str = "gemma4:latest") -> Tuple[str, List[str]]:
    top_chunks, source_node_ids = retrieve_tree(query, root)
    if not top_chunks:
        return "I don't know.", []

    prompt = build_prompt(query, top_chunks)
    answer = generate_answer_ollama(prompt, model=model)
    return answer, source_node_ids


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
        nodes.append(
            {
                "id": node.id,
                "type": "default",
                "data": {
                    "label": format_node_label(node),
                    "text": node.text,
                    "metadata": node.metadata,
                },
                "position": {"x": 0, "y": 0},
            }
        )
        if parent_id is not None:
            edges.append(
                {
                    "id": f"e-{parent_id}-{node.id}",
                    "source": parent_id,
                    "target": node.id,
                }
            )
        for child in node.children:
            walk(child, node.id)

    walk(root)
    return {"nodes": nodes, "edges": edges}
