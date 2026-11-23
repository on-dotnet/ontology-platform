import { Graph, layout } from '@dagrejs/dagre';

import type { components } from '@/api/schema';

export type GraphData = components['schemas']['Graph'];
export type GraphNodeData = components['schemas']['GraphNode'];
export type GraphEdgeData = components['schemas']['GraphEdge'];

export const NODE_WIDTH = 220;
export const NODE_HEIGHT = 84;

export interface PositionedNode {
  node: GraphNodeData;
  /** Top-left corner, as React Flow expects. */
  x: number;
  y: number;
}

/**
 * Edges as drawn: relations go from domain to range; subclass edges go from parent to child, so
 * dagre ranks parents above their children and the arrow sits at the parent end.
 */
export interface DisplayEdge {
  id: string;
  source: string;
  target: string;
  kind: GraphEdgeData['kind'];
  label: string | null;
}

export function displayEdges(data: GraphData): DisplayEdge[] {
  const nodes = new Map(data.nodes.map((node) => [node.id, node]));
  return data.edges
    .filter((edge) => nodes.has(edge.source) && nodes.has(edge.target))
    .map((edge) => {
      if (edge.kind !== 'subclass') return { ...edge };
      // rdfs:subClassOf points child → parent unless the target is the source's child.
      const parentFirst = nodes.get(edge.target)?.parentId === edge.source;
      return parentFirst ? { ...edge } : { ...edge, source: edge.target, target: edge.source };
    });
}

/** Top-to-bottom layered layout of the object types. */
export function layoutGraph(data: GraphData): { nodes: PositionedNode[]; edges: DisplayEdge[] } {
  const edges = displayEdges(data);
  const graph = new Graph();
  graph.setGraph({ rankdir: 'TB', nodesep: 56, ranksep: 88, marginx: 24, marginy: 24 });
  graph.setDefaultEdgeLabel(() => ({}));
  for (const node of data.nodes) graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const edge of edges) {
    if (edge.source !== edge.target) graph.setEdge(edge.source, edge.target);
  }
  layout(graph);
  const nodes = data.nodes.map((node) => {
    const center = graph.node(node.id) as { x?: number; y?: number } | undefined;
    return { node, x: (center?.x ?? 0) - NODE_WIDTH / 2, y: (center?.y ?? 0) - NODE_HEIGHT / 2 };
  });
  return { nodes, edges };
}
