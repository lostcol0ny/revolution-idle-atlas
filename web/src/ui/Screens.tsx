export function LoadingScreen() {
  return (
    <div className="screen" role="status">
      Loading the atlas…
    </div>
  );
}

export function FetchErrorScreen({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="screen" role="alert">
      <h2>Could not load the atlas</h2>
      <p className="muted">{message}</p>
      <button type="button" className="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

export function FormatErrorScreen({ message }: { message: string }) {
  return (
    <div className="screen" role="alert">
      <h2>The atlas data could not be read</h2>
      <p className="muted">{message}</p>
      <p className="muted">
        Trying again will not help — the site and its data file disagree on format.
      </p>
    </div>
  );
}

export function UnknownIdBanner({ what, id }: { what: 'item' | 'system'; id: string }) {
  return (
    <div className="banner" role="alert">
      No {what} with id <code>{id}</code> exists in the atlas. Pick one from the
      sidebar.
    </div>
  );
}
