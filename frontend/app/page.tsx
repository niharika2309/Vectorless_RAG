'use client';

import { useMemo, useState, type ChangeEvent } from 'react';
import RAGVisualizer from '../components/RAGVisualizer';
import { layoutTree, type FlowGraph } from '../lib/TreeProcessor';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

interface UploadResponse {
  sessionId: string;
  reactFlow: FlowGraph;
  documentCount: number;
}

interface QueryResponse {
  answer: string;
  reasoning: string[];
  confidence: number;
  sourceNodeId: string;
  sourceTitle: string;
  sourceHtml: string;
  sourceNodeIds: string[];
}

export default function HomePage() {
  const [sessionId, setSessionId] = useState('');
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState('');
  const [reasoning, setReasoning] = useState<string[]>([]);
  const [confidence, setConfidence] = useState(0);
  const [reactFlow, setReactFlow] = useState<FlowGraph>({ nodes: [], edges: [] });
  const [sourceNodeIds, setSourceNodeIds] = useState<string[]>([]);
  const [hoverTitle, setHoverTitle] = useState('');
  const [hoverHtml, setHoverHtml] = useState('');
  const [hoverVisible, setHoverVisible] = useState(false);
  const [status, setStatus] = useState('Upload documents to start.');

  const positioned = useMemo(() => layoutTree(reactFlow.nodes, reactFlow.edges), [reactFlow]);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files?.length) {
      return;
    }

    setStatus('Uploading files...');
    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append('files', file));

    try {
      const response = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        setStatus(`Upload failed: ${response.status} ${errorText}`);
        return;
      }

      const body = (await response.json()) as UploadResponse;
      setSessionId(body.sessionId);
      setReactFlow(body.reactFlow);
      setSourceNodeIds([]);
      setAnswer('');
      setReasoning([]);
      setConfidence(0);
      setHoverTitle('');
      setHoverHtml('');
      setHoverVisible(false);
      setStatus(`Uploaded ${body.documentCount} document(s) and built the structural tree.`);
    } catch (error) {
      setStatus(`Upload failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  function handleNodeHover(node: any) {
    const nodeHtml = node.data?.html ?? '';
    const nodeLabel = node.data?.label ?? 'Source preview';
    if (nodeHtml) {
      setHoverTitle(nodeLabel);
      setHoverHtml(nodeHtml);
      setHoverVisible(true);
    }
  }

  function handleNodeLeave() {
    setHoverVisible(false);
  }

  function handleNodeClick(node: any) {
    const nodeHtml = node.data?.html ?? '';
    const nodeLabel = node.data?.label ?? 'Source preview';
    if (nodeHtml) {
      setHoverTitle(nodeLabel);
      setHoverHtml(nodeHtml);
      setHoverVisible(true);
    }
  }

  async function runQuery() {
    if (!sessionId) {
      setStatus('Please upload files first.');
      return;
    }

    setStatus('Navigating the tree and querying the document...');
    try {
      const response = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ sessionId, query, model: 'gemma4:latest' }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        setStatus(`Query failed: ${response.status} ${errorText}`);
        return;
      }

      const body = (await response.json()) as QueryResponse;
      setAnswer(body.answer);
      setReasoning(body.reasoning);
      setConfidence(body.confidence);
      setSourceNodeIds(body.sourceNodeIds);
      setHoverTitle(body.sourceTitle);
      setHoverHtml(body.sourceHtml);
      setHoverVisible(true);
      setStatus('Query completed and reasoning path generated.');
    } catch (error) {
      setStatus(`Query failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-3xl font-semibold text-slate-900">The Structural Auditor</h1>
          <p className="mt-2 text-slate-600">Upload a 10-K, inspect its fixed tree, and see the reasoning path used to answer your query.</p>
        </header>

        <section className="grid gap-6">
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <label className="block text-sm font-semibold text-slate-700">Upload document</label>
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              multiple
              onChange={handleUpload}
              className="mt-4 block w-full rounded-3xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900"
            />
            <p className="mt-3 text-sm text-slate-500">Upload a PDF, DOCX, or TXT file to build the fixed document tree.</p>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[2fr_1fr]">
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-900">Document Tree</h2>
              <div className="text-sm text-slate-600">Hover or click nodes for source preview</div>
            </div>
            <div className="relative mt-4 h-[860px] rounded-3xl border border-slate-200 bg-slate-50 p-2">
              <RAGVisualizer
                nodes={positioned.nodes}
                edges={positioned.edges}
                sourceNodeIds={sourceNodeIds}
                onNodeHover={handleNodeHover}
                onNodeLeave={handleNodeLeave}
                onNodeClick={handleNodeClick}
              />
              {hoverVisible && hoverHtml ? (
                <div className="pointer-events-none absolute right-4 top-4 z-20 w-96 rounded-3xl border border-slate-300 bg-white p-4 shadow-2xl">
                  <div className="mb-3 text-sm font-semibold text-slate-900">{hoverTitle}</div>
                  <div className="max-h-72 overflow-auto text-sm leading-6 text-slate-700" dangerouslySetInnerHTML={{ __html: hoverHtml }} />
                </div>
              ) : null}
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-slate-900">Question</h2>
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                rows={5}
                className="mt-4 block w-full rounded-3xl border border-slate-300 bg-slate-50 px-4 py-4 text-sm text-slate-900"
                placeholder="Ask a question about the document structure or content."
              />
              <button
                type="button"
                onClick={runQuery}
                className="mt-4 inline-flex items-center justify-center rounded-3xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white hover:bg-slate-800"
              >
                Run Query
              </button>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold text-slate-900">Reasoning Log</h2>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-700">Confidence: {confidence}%</span>
              </div>
              <div className="mt-4 space-y-2 text-sm text-slate-700">
                {reasoning.length > 0 ? (
                  reasoning.map((line, index) => (
                    <p key={index} className="whitespace-pre-wrap">
                      {line}
                    </p>
                  ))
                ) : (
                  <p className="text-slate-500">Execute a query to see the reasoning path.</p>
                )}
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-slate-900">Answer</h2>
              <p className="mt-4 whitespace-pre-wrap text-slate-700">{answer || 'No answer generated yet.'}</p>
            </div>
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">Session</h2>
              <p className="mt-2 text-slate-700">{sessionId ? `Session ID: ${sessionId}` : 'Upload files to create a session.'}</p>
            </div>
            <p className="text-sm text-slate-500">{status}</p>
          </div>
        </section>
      </div>
    </main>
  );
}
