"use client";

import { useState, useRef, useCallback, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import { layoutTree } from "../lib/TreeProcessor";

/* ─── types ──────────────────────────────────────────────────────────── */
interface SessionState {
  sessionId: string;
  filenames: string[];
  nodes: Node[];
  edges: Edge[];
}

interface QueryResult {
  answer: string;
  sourceNodeIds: string[];
  reasoning: string[];
  confidence: number;
  sourceHtml: string;
  sourceTitle: string;
}

/* ─── helpers ─────────────────────────────────────────────────────────── */
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function nodeColor(type: string) {
  switch (type) {
    case "root": return "#6366f1";
    case "document": return "#10b981";
    case "section": return "#f59e0b";
    case "chunk": return "#64748b";
    default: return "#475569";
  }
}

function nodeStyle(type: string, isHighlighted: boolean) {
  const base = {
    borderRadius: "8px",
    padding: "10px 14px",
    fontSize: "11px",
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontWeight: 500,
    border: `1px solid`,
    cursor: "pointer",
    transition: "all 0.2s",
    maxWidth: "220px",
    wordBreak: "break-word" as const,
  };
  const colors: Record<string, { bg: string; border: string; text: string }> = {
    root:     { bg: "#1e1b4b", border: isHighlighted ? "#a5b4fc" : "#4338ca", text: "#c7d2fe" },
    document: { bg: "#064e3b", border: isHighlighted ? "#6ee7b7" : "#059669", text: "#a7f3d0" },
    section:  { bg: "#451a03", border: isHighlighted ? "#fcd34d" : "#b45309", text: "#fde68a" },
    chunk:    { bg: "#1e293b", border: isHighlighted ? "#94a3b8" : "#334155", text: "#94a3b8" },
  };
  const c = colors[type] ?? colors.chunk;
  return {
    ...base,
    background: c.bg,
    borderColor: isHighlighted ? c.border : c.border,
    color: c.text,
    boxShadow: isHighlighted ? `0 0 16px ${c.border}55` : "none",
    transform: isHighlighted ? "scale(1.04)" : "scale(1)",
  };
}

/* ─── main component ─────────────────────────────────────────────────── */
export default function StructuralAuditor() {
  const [session, setSession] = useState<SessionState | null>(null);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [querying, setQuerying] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"answer" | "reasoning" | "source">("answer");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const positionedGraph = useMemo(() => layoutTree(nodes, edges), [nodes, edges]);

  /* upload */
  const handleUpload = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setUploadError(null);
    setResult(null);

    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));

    try {
      const res = await fetch(`${API}/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
      const data = await res.json();
      const graph = data.reactFlow ?? data;

      const highlighted = new Set<string>();
      const rfNodes: Node[] = graph.nodes.map((n: any) => ({
        id: n.id,
        data: { label: n.data.label, nodeType: n.data.nodeType, text: n.data.text, html: n.data.html },
        position: n.position,
        style: nodeStyle(n.data.nodeType, highlighted.has(n.id)),
      }));
      const rfEdges: Edge[] = graph.edges.map((e: any) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        style: { stroke: "#334155", strokeWidth: 1 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#475569" },
      }));

      const layout = layoutTree(rfNodes, rfEdges);
      setNodes(layout.nodes);
      setEdges(layout.edges);
      setSession({
        sessionId: data.sessionId,
        filenames: Array.from(files).map((f) => f.name),
        nodes: rfNodes,
        edges: rfEdges,
      });
    } catch (e: any) {
      setUploadError(e.message ?? "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [setNodes, setEdges]);

  /* query */
  const handleQuery = useCallback(async () => {
    if (!session || !query.trim()) return;
    setQuerying(true);
    setQueryError(null);

    try {
      const res = await fetch(`${API}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: session.sessionId, query }),
      });
      if (!res.ok) throw new Error(`Query failed: ${res.statusText}`);
      const data = await res.json();
      setResult(data);
      setActiveTab("answer");

      /* highlight source nodes */
      const sourceSet = new Set<string>(data.sourceNodeIds ?? []);
      setNodes((prev) =>
        prev.map((n) => ({
          ...n,
          style: nodeStyle(n.data.nodeType, sourceSet.has(n.id)),
        }))
      );
    } catch (e: any) {
      setQueryError(e.message ?? "Query failed");
    } finally {
      setQuerying(false);
    }
  }, [session, query, setNodes]);

  /* ─── render ──────────────────────────────────────────────────────── */
  return (
    <div style={{
      minHeight: "100vh",
      background: "#0a0e1a",
      color: "#e2e8f0",
      fontFamily: "'Inter', 'DM Sans', sans-serif",
      display: "flex",
      flexDirection: "column",
    }}>

      {/* ── top nav ── */}
      <nav style={{
        borderBottom: "1px solid #1e293b",
        padding: "0 28px",
        height: "56px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "rgba(10,14,26,0.95)",
        backdropFilter: "blur(12px)",
        position: "sticky",
        top: 0,
        zIndex: 100,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {/* icon */}
          <div style={{
            width: 32, height: 32,
            background: "linear-gradient(135deg, #6366f1, #10b981)",
            borderRadius: 8,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 3h12M2 8h8M2 13h5" stroke="#fff" strokeWidth="1.8" strokeLinecap="round"/>
              <circle cx="13" cy="10" r="2.5" stroke="#fff" strokeWidth="1.4"/>
              <path d="M15 12l1.5 1.5" stroke="#fff" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
          </div>
          <span style={{ fontWeight: 600, fontSize: 15, letterSpacing: "-0.01em", color: "#f1f5f9" }}>
            Structural Auditor
          </span>
          <span style={{
            fontSize: 10, fontWeight: 600, padding: "2px 7px",
            background: "#1e293b", color: "#6366f1",
            borderRadius: 4, border: "1px solid #312e81", letterSpacing: "0.05em",
          }}>
            VECTORLESS RAG
          </span>
        </div>

        {session && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {session.filenames.map((f, i) => (
              <span key={i} style={{
                fontSize: 11, padding: "3px 9px",
                background: "#064e3b", color: "#6ee7b7",
                borderRadius: 4, border: "1px solid #065f46",
                fontFamily: "monospace",
              }}>
                {f.length > 22 ? f.slice(0, 20) + "…" : f}
              </span>
            ))}
            <button
              onClick={() => { setSession(null); setResult(null); setNodes([]); setEdges([]); }}
              style={{
                fontSize: 11, padding: "3px 10px",
                background: "transparent", color: "#64748b",
                border: "1px solid #1e293b", borderRadius: 4, cursor: "pointer",
              }}
            >
              ✕ Clear
            </button>
          </div>
        )}
      </nav>

      {/* ── main ── */}
      <main style={{ flex: 1, display: "flex", flexDirection: "column", padding: "28px 28px 0" }}>

        {/* upload zone */}
        {!session && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, gap: 24, paddingBottom: 60 }}>
            <div style={{ textAlign: "center", maxWidth: 520 }}>
              <h1 style={{
                fontSize: 36, fontWeight: 700, letterSpacing: "-0.03em",
                background: "linear-gradient(135deg, #e2e8f0 40%, #6366f1)",
                WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                marginBottom: 10,
              }}>
                Document Intelligence
              </h1>
              <p style={{ color: "#64748b", fontSize: 14, lineHeight: 1.7 }}>
                Upload a 10-K, research report, or any document. The engine parses it into a<br/>
                semantic tree using an LLM — no fixed-size chunking, no vector embeddings.
              </p>
            </div>

            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); handleUpload(e.dataTransfer.files); }}
              onClick={() => fileRef.current?.click()}
              style={{
                width: "100%", maxWidth: 560,
                border: `2px dashed ${dragOver ? "#6366f1" : "#1e293b"}`,
                borderRadius: 16,
                padding: "48px 32px",
                textAlign: "center",
                cursor: "pointer",
                background: dragOver ? "rgba(99,102,241,0.06)" : "rgba(15,23,42,0.6)",
                transition: "all 0.2s",
              }}
            >
              <div style={{
                width: 52, height: 52, margin: "0 auto 16px",
                background: "#1e293b", borderRadius: 12,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M12 15V3M8 7l4-4 4 4" stroke="#6366f1" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M20 15v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4" stroke="#475569" strokeWidth="1.8" strokeLinecap="round"/>
                </svg>
              </div>
              {uploading ? (
                <div>
                  <div style={{ display: "flex", justifyContent: "center", gap: 6, marginBottom: 8 }}>
                    {[0, 1, 2].map(i => (
                      <div key={i} style={{
                        width: 8, height: 8, borderRadius: "50%",
                        background: "#6366f1",
                        animation: "pulse 1.2s ease-in-out infinite",
                        animationDelay: `${i * 0.2}s`,
                      }} />
                    ))}
                  </div>
                  <p style={{ color: "#94a3b8", fontSize: 14 }}>Parsing document tree…</p>
                </div>
              ) : (
                <>
                  <p style={{ color: "#e2e8f0", fontWeight: 500, marginBottom: 6 }}>Drop files here or click to browse</p>
                  <p style={{ color: "#475569", fontSize: 12 }}>PDF · DOCX · TXT — multiple files supported</p>
                </>
              )}
              <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.doc,.txt,.md" style={{ display: "none" }} onChange={(e) => handleUpload(e.target.files)} />
            </div>

            {uploadError && (
              <div style={{ padding: "10px 16px", background: "#450a0a", border: "1px solid #7f1d1d", borderRadius: 8, color: "#fca5a5", fontSize: 13, maxWidth: 560, width: "100%" }}>
                ⚠ {uploadError}
              </div>
            )}

            {/* feature grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, maxWidth: 560, width: "100%", marginTop: 8 }}>
              {[
                { icon: "🌲", title: "Tree Navigation", desc: "Hierarchical doc structure" },
                { icon: "🔍", title: "Semantic Retrieval", desc: "Keyword-scored traversal" },
                { icon: "📍", title: "Audit Trail", desc: "Full reasoning trace" },
              ].map((f) => (
                <div key={f.title} style={{
                  padding: "14px 16px",
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  borderRadius: 10,
                }}>
                  <div style={{ fontSize: 18, marginBottom: 6 }}>{f.icon}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#cbd5e1", marginBottom: 2 }}>{f.title}</div>
                  <div style={{ fontSize: 11, color: "#475569" }}>{f.desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* workspace: graph + panel side by side */}
        {session && (
          <div style={{ display: "flex", gap: 20, flex: 1, minHeight: 0, paddingBottom: 28 }}>

            {/* ── left: graph ── */}
            <div style={{
              flex: "1 1 0", minWidth: 0,
              background: "#0f172a",
              border: "1px solid #1e293b",
              borderRadius: 14,
              overflow: "hidden",
              position: "relative",
            }}>
              <div style={{
                position: "absolute", top: 12, left: 14, zIndex: 10,
                fontSize: 11, color: "#475569", fontFamily: "monospace",
                background: "rgba(15,23,42,0.9)", padding: "4px 10px", borderRadius: 6,
                border: "1px solid #1e293b",
              }}>
                Document Tree · {nodes.length} nodes
              </div>
              <ReactFlow
                nodes={positionedGraph.nodes}
                edges={positionedGraph.edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                fitView
                fitViewOptions={{ padding: 0.15 }}
                minZoom={0.1}
                maxZoom={2.5}
                style={{ background: "transparent" }}
              >
                <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1e293b" />
                <Controls style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }} />
                <MiniMap
                  nodeColor={(n) => nodeColor(n.data?.nodeType ?? "chunk")}
                  style={{ background: "#0a0e1a", border: "1px solid #1e293b", borderRadius: 8 }}
                />
              </ReactFlow>

              {/* legend */}
              <div style={{
                position: "absolute", bottom: 12, left: 14, zIndex: 10,
                display: "flex", gap: 10,
                background: "rgba(15,23,42,0.9)", padding: "6px 12px",
                borderRadius: 8, border: "1px solid #1e293b",
              }}>
                {[
                  { type: "root", color: "#6366f1", label: "Root" },
                  { type: "document", color: "#10b981", label: "Document" },
                  { type: "section", color: "#f59e0b", label: "Section" },
                  { type: "chunk", color: "#64748b", label: "Chunk" },
                ].map((l) => (
                  <div key={l.type} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: l.color }} />
                    <span style={{ fontSize: 10, color: "#64748b" }}>{l.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* ── right: query panel ── */}
            <div style={{ width: 400, flexShrink: 0, display: "flex", flexDirection: "column", gap: 16 }}>

              {/* query input */}
              <div style={{
                background: "#0f172a", border: "1px solid #1e293b",
                borderRadius: 14, padding: "18px 18px 14px",
              }}>
                <label style={{ fontSize: 11, color: "#475569", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", display: "block", marginBottom: 10 }}>
                  Query
                </label>
                <textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleQuery(); }}
                  placeholder="Ask a question about the document…"
                  rows={3}
                  style={{
                    width: "100%", background: "#0a0e1a",
                    border: "1px solid #1e293b", borderRadius: 8,
                    color: "#e2e8f0", fontSize: 13, lineHeight: 1.6,
                    padding: "10px 12px", resize: "none",
                    fontFamily: "inherit", outline: "none",
                    boxSizing: "border-box",
                  }}
                />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10 }}>
                  <span style={{ fontSize: 10, color: "#334155" }}>⌘+Enter to submit</span>
                  <button
                    onClick={handleQuery}
                    disabled={querying || !query.trim()}
                    style={{
                      padding: "8px 20px",
                      background: querying ? "#1e293b" : "linear-gradient(135deg, #4f46e5, #7c3aed)",
                      color: querying ? "#475569" : "#fff",
                      border: "none", borderRadius: 7, cursor: querying ? "not-allowed" : "pointer",
                      fontSize: 13, fontWeight: 600, letterSpacing: "-0.01em",
                      transition: "all 0.15s",
                    }}
                  >
                    {querying ? "Querying…" : "Run Query →"}
                  </button>
                </div>
                {queryError && (
                  <div style={{ marginTop: 8, padding: "7px 10px", background: "#450a0a", border: "1px solid #7f1d1d", borderRadius: 6, color: "#fca5a5", fontSize: 12 }}>
                    {queryError}
                  </div>
                )}
              </div>

              {/* result panel */}
              {result && (
                <div style={{
                  background: "#0f172a", border: "1px solid #1e293b",
                  borderRadius: 14, padding: "16px 18px", flex: 1, minHeight: 0, overflow: "hidden",
                  display: "flex", flexDirection: "column", gap: 12,
                }}>
                  {/* confidence bar */}
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                      <span style={{ fontSize: 10, color: "#475569", letterSpacing: "0.06em", textTransform: "uppercase", fontWeight: 600 }}>Confidence</span>
                      <span style={{ fontSize: 11, color: "#6ee7b7", fontWeight: 600 }}>{result.confidence}%</span>
                    </div>
                    <div style={{ height: 4, background: "#1e293b", borderRadius: 4, overflow: "hidden" }}>
                      <div style={{
                        width: `${result.confidence}%`, height: "100%",
                        background: `linear-gradient(90deg, #059669, ${result.confidence > 70 ? "#10b981" : result.confidence > 40 ? "#f59e0b" : "#ef4444"})`,
                        borderRadius: 4, transition: "width 0.6s ease",
                      }} />
                    </div>
                  </div>

                  {/* tabs */}
                  <div style={{ display: "flex", gap: 2, background: "#0a0e1a", borderRadius: 7, padding: 3 }}>
                    {(["answer", "reasoning", "source"] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        style={{
                          flex: 1, padding: "5px 0", fontSize: 11, fontWeight: 600,
                          border: "none", borderRadius: 5, cursor: "pointer",
                          letterSpacing: "0.04em", textTransform: "capitalize",
                          background: activeTab === tab ? "#1e293b" : "transparent",
                          color: activeTab === tab ? "#e2e8f0" : "#475569",
                          transition: "all 0.15s",
                        }}
                      >
                        {tab === "answer" ? "Answer" : tab === "reasoning" ? "Trace" : "Source"}
                      </button>
                    ))}
                  </div>

                  {/* tab content */}
                  <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
                    {activeTab === "answer" && (
                      <div style={{ fontSize: 13, lineHeight: 1.8, color: "#cbd5e1" }}>
                        {result.answer}
                      </div>
                    )}
                    {activeTab === "reasoning" && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {result.reasoning.map((step, i) => (
                          <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                            <div style={{
                              width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
                              background: "#1e293b", border: "1px solid #334155",
                              display: "flex", alignItems: "center", justifyContent: "center",
                              fontSize: 9, color: "#6366f1", fontWeight: 700,
                            }}>
                              {i + 1}
                            </div>
                            <span style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.7, paddingTop: 1 }}>{step}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {activeTab === "source" && (
                      <div>
                        {result.sourceTitle && (
                          <div style={{ fontSize: 10, color: "#475569", fontFamily: "monospace", marginBottom: 10, padding: "4px 8px", background: "#0a0e1a", borderRadius: 5, border: "1px solid #1e293b" }}>
                            📄 {result.sourceTitle}
                          </div>
                        )}
                        <div
                          dangerouslySetInnerHTML={{ __html: result.sourceHtml }}
                          style={{ fontSize: 12, lineHeight: 1.8, color: "#94a3b8", maxHeight: 360, overflowY: "auto" }}
                        />
                      </div>
                    )}
                  </div>

                  {/* source node ids */}
                  <div style={{ borderTop: "1px solid #1e293b", paddingTop: 10 }}>
                    <div style={{ fontSize: 10, color: "#334155", marginBottom: 6, letterSpacing: "0.05em", textTransform: "uppercase", fontWeight: 600 }}>
                      Source Nodes ({result.sourceNodeIds.length})
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {result.sourceNodeIds.slice(0, 6).map((id) => (
                        <span key={id} style={{
                          fontSize: 9, fontFamily: "monospace",
                          padding: "2px 6px", background: "#1e293b",
                          color: "#6366f1", borderRadius: 3, border: "1px solid #312e81",
                        }}>
                          {id.slice(-12)}
                        </span>
                      ))}
                      {result.sourceNodeIds.length > 6 && (
                        <span style={{ fontSize: 9, color: "#334155", padding: "2px 6px" }}>+{result.sourceNodeIds.length - 6} more</span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* empty state */}
              {!result && (
                <div style={{
                  background: "#0f172a", border: "1px dashed #1e293b",
                  borderRadius: 14, padding: "32px 24px", textAlign: "center", flex: 1,
                }}>
                  <div style={{ fontSize: 28, marginBottom: 10, opacity: 0.4 }}>◌</div>
                  <p style={{ color: "#334155", fontSize: 13, lineHeight: 1.7 }}>
                    Ask a question to see the reasoning trace and highlighted source nodes in the tree.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:0.3;transform:scale(0.8)} 50%{opacity:1;transform:scale(1)} }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 4px; }
        textarea:focus { border-color: #4f46e5 !important; box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important; }
      `}</style>
    </div>
  );
}
