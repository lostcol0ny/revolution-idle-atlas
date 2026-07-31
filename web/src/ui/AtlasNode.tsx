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
      style={{ background: colour }}
      title={`${data.label} — ${data.system} · ${data.kind}`}
    >
      <Handle type="target" position={HandlePosition.Left} />
      {/* role="img" is what makes aria-label binding; on a bare span it is
          advisory and assistive tech may drop it, leaving a lone "R" or "$". */}
      <span className="atlas-node__badge" role="img" aria-label={data.kind}>
        {kindBadge(data.kind)}
      </span>
      <span className="atlas-node__label">{data.label}</span>
      <Handle type="source" position={HandlePosition.Right} />
    </div>
  );
}
