import type { Edge, Node } from 'reactflow';

export interface FlowGraph {
  nodes: Node[];
  edges: Edge[];
}

export function layoutTree(nodes: Node[], edges: Edge[]): FlowGraph {
  const incoming = new Map<string, number>();
  const adjacency = new Map<string, string[]>();

  edges.forEach((edge) => {
    if (edge.target) {
      incoming.set(edge.target.toString(), (incoming.get(edge.target.toString()) || 0) + 1);
    }
    if (edge.source) {
      const source = edge.source.toString();
      adjacency.set(source, [...(adjacency.get(source) || []), edge.target.toString()]);
    }
  });

  const roots = nodes.filter((node) => !incoming.has(node.id));
  const depth = new Map<string, number>();

  const queue = roots.map((root) => ({ id: root.id, level: 0 }));
  queue.forEach((entry) => depth.set(entry.id, entry.level));

  while (queue.length) {
    const entry = queue.shift();
    if (!entry) continue;
    const children = adjacency.get(entry.id) || [];
    children.forEach((childId) => {
      const nextDepth = entry.level + 1;
      if (!depth.has(childId) || depth.get(childId)! > nextDepth) {
        depth.set(childId, nextDepth);
        queue.push({ id: childId, level: nextDepth });
      }
    });
  }

  const levels = new Map<number, Node[]>();
  nodes.forEach((node) => {
    const level = depth.get(node.id) ?? 0;
    levels.set(level, [...(levels.get(level) || []), node]);
  });

  // Calculate node dimensions
  const nodeWidth = 280;
  const nodeHeight = 100;
  const horizontalSpacing = 80;
  const verticalSpacing = 40;

  const positioned = nodes.map((node) => {
    const level = depth.get(node.id) ?? 0;
    const column = levels.get(level) || [];
    const index = column.findIndex((item) => item.id === node.id);
    return {
      ...node,
      position: {
        x: level * (nodeWidth + horizontalSpacing),
        y: index * (nodeHeight + verticalSpacing),
      },
      data: {
        ...node.data,
        label: node.data?.label ?? node.id,
      },
      style: {
        width: `${nodeWidth}px`,
        height: `${nodeHeight}px`,
        padding: '12px',
        fontSize: '12px',
        lineHeight: '1.4',
        wordWrap: 'break-word',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      },
      sourcePosition: 'right',
      targetPosition: 'left',
    };
  });

  return { nodes: positioned, edges };
}
