export function LoadingScreen() {
  return <div className="screen">Loading graph…</div>;
}

export function FetchErrorScreen({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="screen">
      <h2>Could not load the graph</h2>
      <p className="muted">{message}</p>
      <button type="button" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}

export function FormatErrorScreen({ message }: { message: string }) {
  return (
    <div className="screen">
      <h2>This graph file is not usable</h2>
      <p className="muted">{message}</p>
      <p className="muted">
        Retrying will not help — the app and the data file disagree on format.
      </p>
    </div>
  );
}

export function EmptyScreen({
  suggestions,
  onPick,
}: {
  suggestions: { id: string; name: string }[];
  onPick: (id: string) => void;
}) {
  return (
    <div className="screen">
      <h2>Pick a node to trace</h2>
      <p className="muted">
        Upstream dependencies appear on the left, downstream on the right.
      </p>
      {suggestions.length > 0 && (
        <p>
          Try{' '}
          {suggestions.map((node, position) => (
            <span key={node.id}>
              {position > 0 && ', '}
              <button type="button" className="link" onClick={() => onPick(node.id)}>
                {node.name}
              </button>
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

export function UnknownNodeBanner({ nodeId }: { nodeId: string }) {
  return (
    <div className="banner">
      No node with id <code>{nodeId}</code> exists in this graph. Pick one from
      the sidebar.
    </div>
  );
}
