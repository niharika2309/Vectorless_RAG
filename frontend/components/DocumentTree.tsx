'use client';

import { useEffect, useState } from 'react';

interface DocumentNode {
  id: string;
  type: string;
  label: string;
  summary: string;
  html?: string;
  metadata: Record<string, any>;
  children: DocumentNode[];
}

interface DocumentTreeProps {
  tree: DocumentNode | null;
  selectedNodeId: string;
  sourceNodeIds: string[];
  onSelect: (nodeId: string, label: string, html?: string) => void;
}

export default function DocumentTree({ tree, selectedNodeId, sourceNodeIds, onSelect }: DocumentTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!tree) {
      return;
    }

    const initial = new Set<string>();
    initial.add(tree.id);
    tree.children.forEach((child) => initial.add(child.id));
    setExpanded(initial);
  }, [tree]);

  useEffect(() => {
    if (!sourceNodeIds.length) {
      return;
    }

    setExpanded((current) => {
      const next = new Set(current);
      sourceNodeIds.forEach((id) => next.add(id));
      return next;
    });
  }, [sourceNodeIds]);

  function toggleNode(nodeId: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }

  function renderNode(node: DocumentNode, depth = 0) {
    const isExpanded = expanded.has(node.id);
    const isSelected = selectedNodeId === node.id;
    const isActive = sourceNodeIds.includes(node.id);

    return (
      <li key={node.id} className="space-y-2">
        <div
          onClick={() => onSelect(node.id, node.label, node.html)}
          className={`group flex w-full items-start justify-between gap-3 rounded-2xl border px-4 py-3 text-left transition ${
            isSelected ? 'border-slate-900 bg-slate-100' : 'border-slate-200 bg-white hover:border-slate-400'
          }`}
        >
          <span className="flex-1">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-900">
              <span>{node.label}</span>
              {isActive ? <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">active</span> : null}
            </div>
            <p className="mt-1 text-xs text-slate-500">{node.summary}</p>
          </span>
          {node.children.length > 0 ? (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                toggleNode(node.id);
              }}
              className="text-slate-500"
            >
              {isExpanded ? '▾' : '▸'}
            </button>
          ) : null}
        </div>

        {isExpanded && node.children.filter((child) => child.type !== 'chunk').length > 0 ? (
          <ul className="ml-4 border-l border-slate-200 pl-4">
            {node.children
              .filter((child) => child.type !== 'chunk')
              .map((child) => renderNode(child, depth + 1))}
          </ul>
        ) : null}
      </li>
    );
  }

  if (!tree) {
    return <div className="text-sm text-slate-500">Upload documents to see the parsed structural tree.</div>;
  }

  return <ul className="space-y-3">{renderNode(tree)}</ul>;
}
