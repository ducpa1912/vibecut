#!/usr/bin/env node
/**
 * Local S3-compatible object store for development, without Cloudflare.
 *
 * Runs MinIO from Homebrew (`brew install minio`), waits until it answers, then
 * creates the media bucket through the S3 API with the same SigV4 client the API
 * uses. CORS is opened to the Vite origins so the browser can PUT directly.
 *
 * The credentials below are fixed development values. They are not secrets and
 * must never be used for a deployed bucket.
 */
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { AwsClient } from 'aws4fetch';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const host = process.env.DUCKCLEAN_DEV_S3_HOST ?? '127.0.0.1';
const port = Number(process.env.DUCKCLEAN_DEV_S3_PORT ?? 9000);
const consolePort = Number(process.env.DUCKCLEAN_DEV_S3_CONSOLE_PORT ?? 9001);
const accessKeyId = process.env.DUCKCLEAN_DEV_S3_ACCESS_KEY ?? 'duckclean';
const secretAccessKey = process.env.DUCKCLEAN_DEV_S3_SECRET_KEY ?? 'duckclean-dev-secret';
const bucket = process.env.R2_BUCKET ?? 'duckclean-media';
const dataDir = process.env.DUCKCLEAN_DEV_S3_DIR ?? path.join(root, '.dev', 'minio');
const endpoint = `http://${host}:${port}`;

const minio = spawn(
  'minio',
  [
    'server',
    dataDir,
    '--address',
    `${host}:${port}`,
    '--console-address',
    `${host}:${consolePort}`,
  ],
  {
    env: {
      ...process.env,
      MINIO_ROOT_USER: accessKeyId,
      MINIO_ROOT_PASSWORD: secretAccessKey,
      MINIO_API_CORS_ALLOW_ORIGIN: 'http://127.0.0.1:5173,http://localhost:5173',
      MINIO_BROWSER: 'on',
    },
    stdio: ['ignore', 'inherit', 'inherit'],
  },
);

minio.on('error', (error) => {
  console.error(
    error.code === 'ENOENT'
      ? 'minio is not installed. Run `brew install minio`, then try again.'
      : `minio failed to start: ${error.message}`,
  );
  process.exit(1);
});

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitUntilLive() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (minio.exitCode !== null) throw new Error(`minio exited with ${minio.exitCode}`);
    try {
      const response = await fetch(`${endpoint}/minio/health/live`, {
        signal: AbortSignal.timeout(1000),
      });
      if (response.ok) return;
    } catch {
      // not up yet
    }
    await sleep(250);
  }
  throw new Error('minio did not become ready in 15s');
}

try {
  await waitUntilLive();
} catch (error) {
  console.error(error.message);
  minio.kill('SIGTERM');
  process.exit(1);
}

const client = new AwsClient({
  accessKeyId,
  secretAccessKey,
  service: 's3',
  region: 'us-east-1',
});
const created = await client.fetch(`${endpoint}/${bucket}`, { method: 'PUT' });
if (!created.ok && created.status !== 409) {
  const body = await created.text();
  console.error(
    `could not create bucket ${bucket}: ${created.status} ${body.slice(0, 200)}`,
  );
  minio.kill('SIGTERM');
  process.exit(1);
}

console.log(`DuckClean dev object store on ${endpoint} (bucket ${bucket})`);
console.log(`console: http://${host}:${consolePort}`);
console.log('Set these in api/.dev.vars for local mode:');
console.log(`  R2_ENDPOINT=${endpoint}`);
console.log(`  R2_ACCESS_KEY_ID=${accessKeyId}`);
console.log(`  R2_SECRET_ACCESS_KEY=${secretAccessKey}`);

async function stop() {
  minio.kill('SIGTERM');
  process.exit(0);
}
process.on('SIGINT', () => void stop());
process.on('SIGTERM', () => void stop());
