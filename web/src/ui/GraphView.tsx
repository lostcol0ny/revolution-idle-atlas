import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import {
  Background,
  Controls,
  Handle,
  Panel,
  Position as HandlePosition,
  ReactFlow,
  useReactFlow,
} from '@xyflow/react';
import type { Edge, FitViewOptions, Node, NodeProps, NodeTypes } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { GraphIndex } from '../graph/adjacency';
import { breakCycles } from '../graph/cycles';
import { autoDepth, edgeConfidence, ego, fold } from '../graph/ego';
import { layout, NODE_HEIGHT, NODE_WIDTH } from '../graph/layout';
import { BACK_EDGE_STYLE, systemColour } from '../graph/palette';
import type { Depth } from '../graph/urlState';
import { DEPTHS } from '../graph/urlState';
import type { EdgeConfidence, GraphEdge } from '../types';
import type { AtlasFlowNode } from './AtlasNode';
import { AtlasNode } from './AtlasNode';
import './graph.css';

type FoldNodeData = { label: string; system: string };
type FoldFlowNode = Node<FoldNodeData, 'fold'>;

function FoldNode({ data }: NodeProps<FoldFlowNode>) {
  return (
    <div className="fold-node" style={{ background: systemColour(data.system) }}>
      <Handle type="target" position={HandlePosition.Left} />
      <span className="fold-node__badge" aria-hidden="true">
        +
      </span>
      <span className="fold-node__text">
        <span className="fold-node__label">{data.label}</span>
        <span className="fold-node__hint">Click to show all</span>
      </span>
      <Handle type="source" position={HandlePosition.Right} />
    </div>
  );
}

const nodeTypes: NodeTypes = { atlas: AtlasNode, fold: FoldNode };

// Clamped so a crowded view overflows and pans rather than shrinking labels
// below reading size; the Controls still zoom out further on request.
const FIT_OPTIONS: FitViewOptions = { padding: 0.15, minZoom: 0.8, maxZoom: 1.25 };

const ARIA_LABELS = {
  'node.a11yDescription.default': 'Press Enter to open this node.',
};

const CONFIDENCE_STROKE: Record<
  EdgeConfidence,
  { stroke: string; opacity: number; dash?: string }
> = {
  documented: { stroke: 'var(--edge-documented, #e2e8f0)', opacity: 1 },
  provisional: { stroke: 'var(--edge-documented, #e2e8f0)', opacity: 0.6 },
  uncertain: { stroke: 'var(--edge-uncertain, #94a3b8)', opacity: 0.6, dash: '6 5' },
};

function edgeStyle(edge: GraphEdge, isBack: boolean) {
  const confidence = CONFIDENCE_STROKE[edgeConfidence(edge)] ?? CONFIDENCE_STROKE.documented;
  return {
    stroke: isBack ? BACK_EDGE_STYLE.stroke : confidence.stroke,
    strokeOpacity: confidence.opacity,
    strokeDasharray: confidence.dash,
    // `requires` is over half of all edges and the least interesting relation,
    // so it is drawn thinner rather than given a style of its own.
    strokeWidth: edge.rel === 'requires' ? 1.25 : 2,
  };
}

/** Refits after the visible graph changes without the canvas remounting. */
function FitOnChange({ signature }: { signature: string }) {
  const { fitView } = useReactFlow();
  const mounted = useRef(false);
  useEffect(() => {
    // The initial fit is the `fitView` prop's job.
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    void fitView({ ...FIT_OPTIONS, duration: 200 });
  }, [signature, fitView]);
  return null;
}

function Legend({ showGuessed }: { showGuessed: boolean }) {
  const rows: { label: string; stroke: string; opacity: number; dash?: string; width?: number }[] =
    [
      { label: 'Documented', ...CONFIDENCE_STROKE.documented },
      { label: 'Provisional', ...CONFIDENCE_STROKE.provisional },
      ...(showGuessed ? [{ label: 'Guessed', ...CONFIDENCE_STROKE.uncertain }] : []),
      { label: 'Loops back', stroke: BACK_EDGE_STYLE.stroke, opacity: 1 },
      { label: 'Thin: requires', ...CONFIDENCE_STROKE.documented, width: 1.25 },
    ];
  return (
    <Panel position="top-right" className="graph-legend" aria-label="Link legend">
      <ul>
        {rows.map((row) => (
          <li key={row.label}>
            <svg width="28" height="8" aria-hidden="true">
              <line
                x1="0"
                y1="4"
                x2="28"
                y2="4"
                style={{
                  stroke: row.stroke,
                  strokeOpacity: row.opacity,
                  strokeDasharray: row.dash,
                  strokeWidth: row.width ?? 2,
                }}
              />
            </svg>
            {row.label}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

const NO_EXPANSION: ReadonlySet<string> = new Set();

export function GraphView({
  index,
  rootId,
  depth,
  onSelect,
  onDepthChange,
}: {
  index: GraphIndex;
  rootId: string;
  /** null lets the view pick a depth that stays readable. */
  depth: Depth | null;
  onSelect: (nodeId: string) => void;
  onDepthChange: (depth: Depth) => void;
}) {
  const [showGuessed, setShowGuessed] = useState(true);
  // Tagged with the root it belongs to, so navigating away drops it without an
  // effect and coming back starts folded again.
  const [expansion, setExpansion] = useState<{ rootId: string; ids: ReadonlySet<string> }>({
    rootId,
    ids: NO_EXPANSION,
  });
  const expanded = expansion.rootId === rootId ? expansion.ids : NO_EXPANSION;

  const systemNames = useMemo(
    () => new Map(index.systems.map((system) => [system.id, system.name])),
    [index],
  );

  const effectiveDepth = useMemo<Depth>(
    () => depth ?? autoDepth(index, rootId, { includeUncertain: showGuessed }),
    [depth, index, rootId, showGuessed],
  );

  const { nodes, edges, groupIds, canRegroup } = useMemo(() => {
    const folded = fold(
      ego(index, rootId, effectiveDepth, { includeUncertain: showGuessed }),
      expanded,
    );
    const { dag, backEdges } = breakCycles(folded);
    const positions = layout(dag);
    const back = new Set(backEdges);
    const systemName = (id: string) => systemNames.get(id) ?? id;

    const flowNodes = folded.nodes.map(({ node }): AtlasFlowNode | FoldFlowNode => {
      const common = {
        id: node.id,
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        ariaRole: 'button' as const,
      };
      const group = folded.groups.get(node.id);
      if (group !== undefined) {
        const label = `${group.members.length} from ${systemName(group.system)}`;
        return {
          ...common,
          type: 'fold',
          ariaLabel: `${label}, collapsed. Expand to show each one.`,
          data: { label, system: group.system },
        };
      }
      const isRoot = node.id === rootId;
      return {
        ...common,
        type: 'atlas',
        ariaLabel: `${node.name}, ${systemName(node.system)}${isRoot ? ', current node' : ''}`,
        data: { label: node.name, system: node.system, kind: node.kind, isRoot },
      };
    });

    const flowEdges: Edge[] = folded.edges.map((edge, position) => ({
      id: `${edge.from}|${edge.to}|${edge.rel}|${position}`,
      source: edge.from,
      target: edge.to,
      style: edgeStyle(edge, back.has(edge)),
      // Only the relation the line style does not already carry is labelled;
      // a label on every `boosts` edge buries the canvas.
      label: edge.rel === 'unlocks' ? 'unlocks' : undefined,
      labelStyle: { fontSize: 11, fill: 'var(--muted, #94a3b8)' },
      labelBgStyle: { fill: 'var(--bg, #0f172a)' },
    }));

    return {
      nodes: flowNodes,
      edges: flowEdges,
      groupIds: new Set(folded.groups.keys()),
      canRegroup: folded.unfolded.length > 0,
    };
  }, [index, rootId, effectiveDepth, showGuessed, expanded, systemNames]);

  const activate = (id: string) => {
    if (groupIds.has(id)) {
      setExpansion({ rootId, ids: new Set([...expanded, id]) });
    } else {
      onSelect(id);
    }
  };

  // React Flow focuses nodes but only selects them on Enter; this makes Enter
  // and Space do what a click does.
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const target = event.target as HTMLElement;
    const id = target.classList.contains('react-flow__node') ? target.dataset.id : undefined;
    if (id === undefined) return;
    event.preventDefault();
    activate(id);
  };

  return (
    <div className="graphview">
      <div className="graphview__toolbar">
        <span className="muted" id="graphview-depth">
          Depth
        </span>
        <div role="group" aria-labelledby="graphview-depth" className="graphview__depths">
          {DEPTHS.map((value) => (
            <button
              key={value}
              type="button"
              className={value === effectiveDepth ? 'chip chip--on' : 'chip'}
              aria-pressed={value === effectiveDepth}
              onClick={() => onDepthChange(value)}
            >
              {value}
            </button>
          ))}
        </div>
        {depth === null && <span className="muted">(auto)</span>}
        <label className="graphview__toggle">
          <input
            type="checkbox"
            checked={showGuessed}
            onChange={(event) => setShowGuessed(event.target.checked)}
          />
          Show guessed links
        </label>
        {canRegroup && (
          <button
            type="button"
            className="chip"
            onClick={() => setExpansion({ rootId, ids: NO_EXPANSION })}
          >
            Regroup
          </button>
        )}
        <span className="muted graphview__count" aria-live="polite">
          {nodes.length} nodes · {edges.length} links
        </span>
      </div>
      <div className="graphview__canvas" onKeyDown={onKeyDown}>
        <ReactFlow
          key={rootId}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          // Themes the parts this file does not draw: the Controls buttons, the
          // Background dots and the attribution link all ship their own light
          // defaults and stay light without it.
          colorMode="dark"
          fitView
          fitViewOptions={FIT_OPTIONS}
          minZoom={0.2}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesFocusable={false}
          deleteKeyCode={null}
          ariaLabelConfig={ARIA_LABELS}
          proOptions={{ hideAttribution: false }}
          onNodeClick={(_event, node) => activate(node.id)}
        >
          <Background />
          <Controls showInteractive={false} fitViewOptions={FIT_OPTIONS} />
          <Legend showGuessed={showGuessed} />
          <FitOnChange signature={`${effectiveDepth}|${showGuessed}|${[...expanded].join()}`} />
        </ReactFlow>
      </div>
    </div>
  );
}
