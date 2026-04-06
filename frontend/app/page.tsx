'use client';

import { useMemo, useState, type ChangeEvent } from 'react';
import RAGVisualizer from '../components/RAGVisualizer';
import { layoutTree, type FlowGraph } from '../lib/TreeProcessor';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export default function HomePage() {
  const [sessionId, setSessionId] = useState('');
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState('');
  const [reactFlow, setReactFlow] = useState<FlowGraph>({ nodes: [], edges: [] });
  const [sourceNodeIds, setSourceNodeIds] = useState<string[]>([]);
  const [status, setStatus] = useState('Upload files to start.');
  const [treeSummary, setTreeSummary] = useState({ nodes: 0, edges: 0 });

  const positioned = useMemo(() => layoutTree(reactFlow.nodes, reactFlow.edges), [reactFlow]);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files?.length) {
      return;
    }

    setStatus('Uploading files...');
    const formData = new FormData();

    Array.from(files).forEach((file) => {
      formData.append('files', file);
    });

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

      const body = await response.json();
      setSessionId(body.sessionId);
      setReactFlow(body.reactFlow);
      setSourceNodeIds([]);
      setAnswer('');
      setTreeSummary({ nodes: body.reactFlow.nodes.length, edges: body.reactFlow.edges.length });
      setStatus(`Uploaded ${body.documentCount} documents and built ${body.reactFlow.nodes.length} tree nodes.`);
    } catch (error) {
      setStatus(`Upload failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function runQuery() {
    if (!sessionId) {
      setStatus('Please upload files first.');
      return;
    }

    setStatus('Querying tree...');
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

      const body = await response.json();
      setAnswer(body.answer);
      setSourceNodeIds(body.sourceNodeIds);
      setStatus('Query completed.');
    } catch (error) {
      setStatus(`Query failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-3xl font-semibold text-slate-900">Vectorless RAG</h1>
          <p className="mt-2 text-slate-600">
            Upload PDF, DOCX, or TXT files, then ask the backend to retrieve the most relevant content and highlight the search path in the tree.
          </p>
        </header>

        <section className="grid gap-6 md:grid-cols-2">
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <label className="block text-sm font-medium text-slate-700">Upload documents</label>
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              multiple
              onChange={handleUpload}
              className="mt-3 block w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900"
            />
            <p className="mt-3 text-sm text-slate-500">Upload one or more files and let the backend convert them into a tree.</p>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <label className="block text-sm font-medium text-slate-700">Ask a question</label>
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              rows={4}
              className="mt-3 block w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900"
            />
            <button
              type="button"
              onClick={runQuery}
              className="mt-4 inline-flex items-center justify-center rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
            >
              Run Query
            </button>
            <p className="mt-3 text-sm text-slate-500">The backend returns an answer and the node path IDs used to build the highlighted flow.</p>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-900">Document Tree</h2>
              <div className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600">
                {treeSummary.nodes} nodes • {treeSummary.edges} edges
              </div>
            </div>
            <div className="mt-4 h-[640px] rounded-3xl border border-slate-200 bg-slate-50 p-2">
              <RAGVisualizer nodes={positioned.nodes} edges={positioned.edges} sourceNodeIds={sourceNodeIds} />
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-slate-900">Answer</h2>
              <p className="mt-3 whitespace-pre-wrap text-slate-700">{answer || 'No query answer yet.'}</p>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-slate-900">Session</h2>
              <p className="mt-3 text-slate-700">{sessionId ? `Current session: ${sessionId}` : 'Upload files to create a session.'}</p>
              <p className="mt-2 text-sm text-slate-500">{status}</p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
