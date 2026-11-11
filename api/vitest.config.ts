import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['test/**/*.test.ts'],
    // Each suite starts a real in-process Postgres (PGlite) and runs the
    // migrations against it; that is seconds of WASM work, not a hung test.
    testTimeout: 30_000,
    hookTimeout: 60_000,
  },
});
