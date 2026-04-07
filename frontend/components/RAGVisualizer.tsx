'use client';

import { useEffect } from 'react';
import ReactFlow, { Background, Controls, Node, Edge, useEdgesState, useNodesState } from 'reactflow';
import 'reactflow/dist/style.css';

interface RAGVisualizerProps {
  nodes: Node[];
  edges: Edge[];
  sourceNodeIds: string[];
  onNodeHover?: (node: Node) => void;
  onNodeLeave?: () => void;
  onNodeClick?: (node: Node) => void;
}

export default function RAGVisualizer({ nodes, edges, sourceNodeIds, onNodeHover, onNodeLeave, onNodeClick }: RAGVisualizerProps) {
  const [rfNodes, setNodes, onNodesChange] = useNodesState(nodes);
  const [rfEdges, setEdges, onEdgesChange] = useEdgesState(edges);

  useEffect(() => {
    setNodes(nodes);
  }, [nodes, setNodes]);

  useEffect(() => {
    setEdges(edges);
  }, [edges, setEdges]);

  useEffect(() => {
    setNodes((current) =>
      current.map((node) => ({
        ...node,
        style: sourceNodeIds.includes(node.id)
          ? {
              border: '2px solid #16a34a',
              background: '#dcfce7',
              color: '#14532d',
            }
          : {
              border: '1px solid #cbd5e1',
              background: '#ffffff',
              color: '#0f172a',
            },
      }))
    );

    setEdges((current) =>
      current.map((edge) => ({
        ...edge,
        animated: sourceNodeIds.includes(edge.source) && sourceNodeIds.includes(edge.target),
        style: sourceNodeIds.includes(edge.source) && sourceNodeIds.includes(edge.target)
          ? { stroke: '#16a34a', strokeWidth: 3 }
          : { stroke: '#94a3b8', strokeWidth: 1 },
      }))
    );
  }, [sourceNodeIds, setEdges, setNodes]);

  return (
    <div className="h-full w-full rounded-3xl bg-white">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeMouseEnter={(_, node) => onNodeHover?.(node)}
        onNodeMouseLeave={() => onNodeLeave?.()}
        onNodeClick={(_, node) => onNodeClick?.(node)}
        fitView
      >
        <Background gap={16} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
