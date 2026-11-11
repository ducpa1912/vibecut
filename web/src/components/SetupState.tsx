export function SetupState() {
  return (
    <main className="setup">
      <p className="wordmark">DuckClean</p>
      <h1>Sign-in is not configured.</h1>
      <p className="muted">
        The M1 surface is built, but this build has no Clerk publishable key. Set
        <code>VITE_CLERK_PUBLISHABLE_KEY</code> and rebuild. No sign-in button is shown
        because there is nothing real behind it.
      </p>
      <pre>
        <code>VITE_CLERK_PUBLISHABLE_KEY=pk_test_...</code>
      </pre>
    </main>
  );
}
