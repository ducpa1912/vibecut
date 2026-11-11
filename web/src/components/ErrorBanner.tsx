export function ErrorBanner({
  error,
  onRetry,
}: {
  error: { code: string; message: string; action: string };
  onRetry: () => void;
}) {
  return (
    <div className="error-banner" role="alert">
      <span>{error.message}</span>
      {error.action === 'retry' ? (
        <button className="link" type="button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}
