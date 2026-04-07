'use client';

import { useEffect, useState } from 'react';
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
  const [hoveredNode, setHoveredNode] = useState<Node | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });

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
  const handleNodeMouseEnter = (event: React.MouseEvent, node: Node) => {
    setHoveredNode(node);
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    setTooltipPosition({ x: rect.left, y: rect.top });
    onNodeHover?.(node);
  };

  const handleNodeMouseLeave = () => {
    setHoveredNode(null);
    onNodeLeave?.();
  };

  return (
    <div className="h-full w-full rounded-3xl bg-white relative">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        onNodeClick={(_, node) => onNodeClick?.(node)}
        fitView
      >
        <Background gap={16} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
      
      {hoveredNode && hoveredNode.data?.text && (
        <div className="fixed z-50 max-w-sm rounded-lg border border-slate-300 bg-white p-3 shadow-lg pointer-events-none" 
             style={{
               left: `${tooltipPosition.x + 10}px`,
               top: `${tooltipPosition.y - 10}px`,
             }}>
          <p className="text-xs leading-relaxed text-slate-700 max-h-64 overflow-y-auto">
            {hoveredNode.data.text}
          </p>
        </div>
      )}d gap={16} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
