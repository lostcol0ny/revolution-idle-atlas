import { useMemo } from 'react';
import { Background, Controls, ReactFlow } from '@xyflow/react';
import type { Edge, NodeTypes } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { GraphIndex } from '../graph/adjacency';
import { breakCycles } from '../graph/cycles';
import { ego } from '../graph/ego';
import { layout, NODE_HEIGHT, NODE_WIDTH } from '../graph/layout';
import { BACK_EDGE_STYLE, REL_STYLE } from '../graph/palette';
import type { Depth } from '../graph/urlState';
import { DEPTHS } from '../graph/urlState';
import type { AtlasFlowNode } from './AtlasNode';
import { AtlasNode } from './AtlasNode';

const nodeTypes: NodeTypes = { atlas: AtlasNode };

export function GraphView({
  index,
  rootId,
  depth,
  onSelect,
  onDepthChange,
}: {
  index: GraphIndex;
  rootId: string;
  depth: Depth;
  onSelect: (nodeId: string) => void;
  onDepthChange: (depth: Depth) => void;
}) {
  const { nodes, edges } = useMemo(() => {
    const subgraph = ego(index, rootId, depth);
    const { dag, backEdges } = breakCycles(subgraph);
    const positions = layout(dag);
    const back = new Set(backEdges);

    const flowNodes: AtlasFlowNode[] = subgraph.nodes.map(({ node }) => ({
      id: node.id,
      type: 'atlas',
      position: positions.get(node.id) ?? { x: 0, y: 0 },
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      data: {
        label: node.name,
        system: node.system,
        kind: node.kind,
        isRoot: node.id === rootId,
      },
    }));

    const flowEdges: Edge[] = subgraph.edges.map((edge, position) => {
      const isBack = back.has(edge);
      const style = isBack ? BACK_EDGE_STYLE : REL_STYLE[edge.rel];
      return {
        id: `${edge.from}|${edge.to}|${edge.rel}|${position}`,
        source: edge.from,
        target: edge.to,
        animated: false,
        style: {
          stroke: style.stroke,
          strokeWidth: style.width,
          strokeDasharray: style.dash,
        },
        label: edge.rel === 'requires' ? undefined : edge.rel,
        labelStyle: { fontSize: 10, fill: '#475569' },
      };
    });

    return { nodes: flowNodes, edges: flowEdges };
  }, [index, rootId, depth]);

  return (
    <div className="graphview">
      <div className="graphview__toolbar">
        <span className="muted">Depth</span>
        {DEPTHS.map((value) => (
          <button
            key={value}
            type="button"
            className={value === depth ? 'chip chip--on' : 'chip'}
            onClick={() => onDepthChange(value)}
          >
            {value}
          </button>
        ))}
        <span className="muted">
          {nodes.length} nodes · {edges.length} edges
        </span>
      </div>
      <ReactFlow
        key={`${rootId}:${depth}`}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        proOptions={{ hideAttribution: false }}
        onNodeClick={(_event, node) => onSelect(node.id)}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
