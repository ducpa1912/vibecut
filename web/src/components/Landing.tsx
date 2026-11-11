import { useClerk } from '@clerk/react';

export function Landing() {
  const { openSignIn } = useClerk();
  return (
    <main className="landing">
      <p className="wordmark">DuckClean</p>
      <h1>Remove baked-in text, logos and burnt-in images from video.</h1>
      <p className="lede">
        Upload the full clip. DuckClean finds the marks, renders only the beats that
        contain them, and returns the whole video with the original audio.
      </p>
      <button className="primary" type="button" onClick={() => openSignIn()}>
        Sign in
      </button>
      <p className="fine">
        A phone can upload, review, render and download because rendering is remote.
      </p>
    </main>
  );
}
