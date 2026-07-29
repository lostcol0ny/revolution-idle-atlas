import type { GraphIndex } from '../graph/adjacency';
import type { GraphEdge, GraphNode } from '../types';
import { sourceLabel, wikiUrl } from '../graph/wiki';

function EdgeRow({
  edge,
  otherId,
  index,
  onSelect,
}: {
  edge: GraphEdge;
  otherId: string;
  index: GraphIndex;
  onSelect: (nodeId: string) => void;
}) {
  const other = index.nodes.get(otherId);
  const source = sourceLabel(edge.source);
  const confidence = edge.confidence ?? 'documented';

  return (
    <li className="edgerow">
      <div className="edgerow__line">
        <span className="edgerow__rel">{edge.rel}</span>
        <span className="sep">·</span>
        <button type="button" className="link" onClick={() => onSelect(otherId)}>
          {other ? other.name : otherId}
        </button>
        <span className="sep">·</span>
        {source.href ? (
          <a className="link" href={source.href} target="_blank" rel="noreferrer noopener">
            {source.text}
          </a>
        ) : (
          <span className="muted">{source.text}</span>
        )}
        <span className="sep">·</span>
        <span className="muted">{confidence}</span>
      </div>
      {edge.note !== undefined && <div className="edgerow__note">{edge.note}</div>}
    </li>
  );
}

export function NodeCard({
  index,
  node,
  onSelect,
}: {
  index: GraphIndex;
  node: GraphNode;
  onSelect: (nodeId: string) => void;
}) {
  const incoming = index.incoming.get(node.id) ?? [];
  const outgoing = index.outgoing.get(node.id) ?? [];
  const href = wikiUrl(node.wiki);
  // Matches the pipeline, which is the authority on what an absent field means:
  // models.py defaults both node and edge confidence to `documented`. Rendering
  // an absent value as 'unknown' would relabel every documented node the day the
  // field stops being emitted.
  const confidence = node.confidence ?? 'documented';

  return (
    <div className="nodecard">
      <h2 className="nodecard__name">{node.name}</h2>
      <dl className="nodecard__facts">
        <dt>id</dt>
        <dd>
          <code>{node.id}</code>
        </dd>
        <dt>system</dt>
        <dd>{node.system}</dd>
        <dt>kind</dt>
        <dd>{node.kind}</dd>
        <dt>confidence</dt>
        <dd>{confidence}</dd>
      </dl>

      {href !== null && (
        <p>
          <a className="link" href={href} target="_blank" rel="noreferrer noopener">
            Open on the wiki
          </a>
        </p>
      )}

      <h3 className="nodecard__heading">Feeds this ({incoming.length})</h3>
      {incoming.length === 0 ? (
        <p className="muted">Nothing documented feeds this node.</p>
      ) : (
        <ul className="edgelist">
          {incoming.map((edge, position) => (
            <EdgeRow
              key={`in-${position}`}
              edge={edge}
              otherId={edge.from}
              index={index}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}

      <h3 className="nodecard__heading">This feeds ({outgoing.length})</h3>
      {outgoing.length === 0 ? (
        <p className="muted">This node feeds nothing documented.</p>
      ) : (
        <ul className="edgelist">
          {outgoing.map((edge, position) => (
            <EdgeRow
              key={`out-${position}`}
              edge={edge}
              otherId={edge.to}
              index={index}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
