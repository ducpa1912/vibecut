/**
 * M0 shell only. The library, upload and review screens are built after the
 * contract (api/migrations, api/openapi.yaml, worker schemas) is frozen.
 *
 * Nothing here may show fake progress, a fake frame, a fake voice or a fake
 * success state. There is no video pipeline wired up yet.
 */
export function App() {
  return (
    <main className="shell">
      <h1>DuckClean</h1>
      <p className="lede">Remove baked-in text, logos and burnt-in images from video.</p>
      <p className="status">
        M0 — contract in progress. Upload, review and render screens are not built yet.
      </p>
    </main>
  );
}
