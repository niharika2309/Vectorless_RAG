import uuid
from typing import Any, Dict, List

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag import build_document_tree, flatten_tree_to_react_flow, query_tree

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
    documentCount: int


class QueryRequest(BaseModel):
    sessionId: str
    query: str
    model: str = "gemma4:latest"


class QueryResponse(BaseModel):
    answer: str
    sourceNodeIds: List[str]


@app.post("/upload", response_model=UploadResponse)
async def upload_documents(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    documents = []
    for upload in files:
        raw_bytes = await upload.read()
        documents.append({"filename": upload.filename, "content": raw_bytes})

    root = build_document_tree(documents)
    react_flow = flatten_tree_to_react_flow(root)
    session_id = str(uuid.uuid4())
    app.state.sessions[session_id] = {"root": root, "reactFlow": react_flow}

    return {
        "sessionId": session_id,
        "reactFlow": react_flow,
        "documentCount": len(documents),
    }


@app.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest = Body(...)):
    session = app.state.sessions.get(request.sessionId)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Upload files first.")

    answer, source_node_ids = query_tree(request.query, session["root"], model=request.model)
    return {
        "answer": answer,
        "sourceNodeIds": source_node_ids,
    }
