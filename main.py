import uuid
from typing import Any, Dict, List

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag import (
    build_document_tree,
    extract_document_text,
    flatten_tree_to_react_flow,
    query_tree,
    save_markdown_export,
    serialize_tree,
    convert_text_to_markdown,
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.sessions = {}


class UploadResponse(BaseModel):
    sessionId: str
    reactFlow: Dict[str, Any]
    documentTree: Dict[str, Any]
    documentCount: int
    markdownFiles: List[str]


class QueryRequest(BaseModel):
    sessionId: str
    query: str
    model: str = "gemma-e4b"


class QueryResponse(BaseModel):
    answer: str
    reasoning: List[str]
    confidence: int
    sourceNodeId: str
    sourceTitle: str
    sourceHtml: str
    sourceNodeIds: List[str]


@app.post("/upload", response_model=UploadResponse)
async def upload_documents(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    documents = []
    markdown_files: List[str] = []
    for upload in files:
        raw_bytes = await upload.read()
        filename = upload.filename
        documents.append({"filename": filename, "content": raw_bytes})

        text = extract_document_text(filename, raw_bytes)
        markdown_text = convert_text_to_markdown(text)
        markdown_files.append(save_markdown_export(filename, markdown_text))

    root = build_document_tree(documents)
    react_flow = flatten_tree_to_react_flow(root)
    document_tree = serialize_tree(root)
    session_id = str(uuid.uuid4())
    app.state.sessions[session_id] = {"root": root, "reactFlow": react_flow, "documentTree": document_tree}

    return {
        "sessionId": session_id,
        "reactFlow": react_flow,
        "documentTree": document_tree,
        "documentCount": len(documents),
        "markdownFiles": markdown_files,
    }


@app.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest = Body(...)):
    session = app.state.sessions.get(request.sessionId)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Upload files first.")

    answer, source_node_ids, reasoning, confidence, source_html, source_node_id, source_title = query_tree(
        request.query,
        session["root"],
        model=request.model,
    )
    return {
        "answer": answer,
        "reasoning": reasoning,
        "confidence": confidence,
        "sourceNodeId": source_node_id,
        "sourceTitle": source_title,
        "sourceHtml": source_html,
        "sourceNodeIds": source_node_ids,
    }
