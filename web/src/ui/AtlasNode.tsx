import { Handle, Position as HandlePosition } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import type { Kind, System } from '../types';
import { kindBadge, systemColour } from '../graph/palette';

/**
 * Declared as a `type` alias, not an `interface`. React Flow v12 constrains
 * node data to `Record<string, unknown>`, and only type aliases receive the
 * implicit index signature that satisfies it. An interface here fails to
 * typecheck with a confusing "index signature is missing" error.
 */
export type AtlasNodeData = {
  label: string;
  system: System;
  kind: Kind;
  isRoot: boolean;
};

export type AtlasFlowNode = Node<AtlasNodeData, 'atlas'>;

export function AtlasNode({ data }: NodeProps<AtlasFlowNode>) {
  const colour = systemColour(data.system);
  return (
    <div
      className={data.isRoot ? 'atlas-node atlas-node--root' : 'atlas-node'}
      style={
        data.isRoot
          ? { background: colour, borderColor: '#0f172a' }
          : { background: colour, borderColor: colour }
      }
      title={`${data.label} — ${data.system} · ${data.kind}`}
    >
      <Handle type="target" position={HandlePosition.Left} />
      <span className="atlas-node__badge">{kindBadge(data.kind)}</span>
      <span className="atlas-node__label">{data.label}</span>
      <Handle type="source" position={HandlePosition.Right} />
    </div>
  );
}
