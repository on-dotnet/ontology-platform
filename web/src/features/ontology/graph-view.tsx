import '@xyflow/react/style.css';

import {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import { Maximize, ZoomIn, ZoomOut, type LucideIcon } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Tooltip } from '@/components/ui/tooltip';
import { cn } from '@/lib/cn';
import { useTheme } from '@/theme/theme-provider';

import { layoutGraph, NODE_HEIGHT, NODE_WIDTH, type GraphData } from './graph-layout';

type EntityNodeData = { label: string; localName: string | null; propertyCount: number };
type EntityNode = Node<EntityNodeData, 'entityType'>;

/** An object type card. Handles are invisible: the graph is read-only. */
function EntityTypeNode({ data, selected }: NodeProps<EntityNode>) {
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        'flex flex-col justify-center rounded-xl border border-l-4 border-l-primary bg-card px-3.5 py-2 text-left shadow-card transition-colors',
        selected ? 'border-primary ring-2 ring-primary/40' : 'border-border hover:border-primary/60',
      )}
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
    >
      <Handle type="target" position={Position.Top} isConnectable={false} className="opacity-0" />
      <p className="truncate text-sm font-semibold text-foreground">{data.label}</p>
      <p className="truncate font-mono text-xs text-muted-foreground">{data.localName}</p>
      <p className="mt-1 text-xs text-primary-strong">{t('ontologyPage.graph.propertyCount', { count: data.propertyCount })}</p>
      <Handle type="source" position={Position.Bottom} isConnectable={false} className="opacity-0" />
    </div>
  );
}

const nodeTypes = { entityType: EntityTypeNode };

const RELATION_STROKE = 'var(--muted-foreground)';
const SUBCLASS_STROKE = 'var(--primary)';

function toFlow(data: GraphData): { nodes: EntityNode[]; edges: Edge[] } {
  const { nodes, edges } = layoutGraph(data);
  return {
    nodes: nodes.map(({ node, x, y }) => ({
      id: node.id,
      type: 'entityType',
      position: { x, y },
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      data: { label: node.label, localName: node.localName, propertyCount: node.propertyCount },
    })),
    edges: edges.map((edge) => {
      const subclass = edge.kind === 'subclass';
      const stroke = subclass ? SUBCLASS_STROKE : RELATION_STROKE;
      const marker = { type: MarkerType.ArrowClosed, color: stroke, width: 16, height: 16 };
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: 'smoothstep',
        ...(subclass ? { markerStart: marker } : { markerEnd: marker }),
        ...(edge.label && !subclass ? { label: edge.label } : {}),
        style: { stroke, strokeWidth: 1.5, ...(subclass ? { strokeDasharray: '6 4' } : {}) },
        labelStyle: { fill: 'var(--foreground)', fontSize: 12, fontWeight: 500 },
        labelBgStyle: { fill: 'var(--card)' },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 6,
        className: subclass ? 'graph-edge-subclass' : 'graph-edge-relation',
      };
    }),
  };
}

function ControlButton({ label, icon: Icon, onClick }: { label: string; icon: LucideIcon; onClick: () => void }) {
  return (
    <Tooltip content={label} side="left">
      <Button variant="ghost" size="icon-sm" aria-label={label} onClick={onClick}>
        <Icon aria-hidden />
      </Button>
    </Tooltip>
  );
}

function GraphControls() {
  const { t } = useTranslation();
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  return (
    <Panel position="top-right" className="flex flex-col gap-0.5 rounded-lg border border-border bg-card p-1 shadow-card">
      <ControlButton label={t('ontologyPage.graph.zoomIn')} icon={ZoomIn} onClick={() => void zoomIn()} />
      <ControlButton label={t('ontologyPage.graph.zoomOut')} icon={ZoomOut} onClick={() => void zoomOut()} />
      <ControlButton label={t('ontologyPage.graph.fitView')} icon={Maximize} onClick={() => void fitView()} />
    </Panel>
  );
}

function GraphLegend() {
  const { t } = useTranslation();
  return (
    <Panel position="bottom-left" className="flex items-center gap-4 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground shadow-card">
      <span className="flex items-center gap-1.5">
        <svg width="24" height="8" aria-hidden className="stroke-muted-foreground">
          <line x1="0" y1="4" x2="24" y2="4" strokeWidth="1.5" />
        </svg>
        {t('ontologyPage.graph.legendRelation')}
      </span>
      <span className="flex items-center gap-1.5">
        <svg width="24" height="8" aria-hidden className="stroke-primary">
          <line x1="0" y1="4" x2="24" y2="4" strokeWidth="1.5" strokeDasharray="6 4" />
        </svg>
        {t('ontologyPage.graph.legendSubclass')}
      </span>
    </Panel>
  );
}

interface GraphViewProps {
  graph: GraphData;
  onSelect: (elementId: string) => void;
}

/** Object types as cards, relations as arrows and parent types as dashed arrows; zoom, pan and fit. */
export function GraphView({ graph, onSelect }: GraphViewProps) {
  const { t } = useTranslation();
  const { resolved } = useTheme();
  const flow = useMemo(() => toFlow(graph), [graph]);
  // Remount when the graph changes so the uncontrolled flow picks up the new layout and fits again.
  const signature = useMemo(
    () => [...graph.nodes.map((node) => node.id), '|', ...graph.edges.map((edge) => edge.id)].join(','),
    [graph],
  );

  return (
    <div
      className="ontology-graph h-[min(70dvh,44rem)] min-h-96 w-full overflow-hidden rounded-xl border border-border bg-background"
      role="figure"
      aria-label={t('ontologyPage.graph.label', { nodes: graph.nodes.length, edges: graph.edges.length })}
    >
      <ReactFlow
        key={signature}
        defaultNodes={flow.nodes}
        defaultEdges={flow.edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        maxZoom={2}
        nodesConnectable={false}
        deleteKeyCode={null}
        forceColorMode={resolved}
        onNodeClick={(_, node) => onSelect(node.id)}
        ariaLabelConfig={{
          'node.a11yDescription.default': t('ontologyPage.graph.a11yNode'),
          'node.a11yDescription.keyboardDisabled': t('ontologyPage.graph.a11yNode'),
          'edge.a11yDescription.default': t('ontologyPage.graph.a11yEdge'),
          'handle.ariaLabel': t('ontologyPage.graph.a11yHandle'),
        }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.5} color="var(--border)" />
        <GraphControls />
        <GraphLegend />
      </ReactFlow>
    </div>
  );
}
