#!/usr/bin/env node
/**
 * Development Postgres without a Cloudflare account.
 *
 * PGlite is Postgres compiled to WASM; pglite-socket exposes it on a TCP port so
 * `wrangler dev` can reach it through the Hyperdrive `localConnectionString`.
 * The migrations are the same SQL files production runs, applied once each and
 * recorded in `dev_schema_migrations`. This is a development server, not a
 * production database: it is single-process and lives under `.dev/`.
 */
import { mkdir, readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { PGlite } from '@electric-sql/pglite';
import { PGLiteSocketServer } from '@electric-sql/pglite-socket';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataDir = process.env.DUCKCLEAN_DEV_DB_DIR ?? path.join(root, '.dev', 'pgdata');
const port = Number(process.env.DUCKCLEAN_DEV_DB_PORT ?? 5432);
const host = process.env.DUCKCLEAN_DEV_DB_HOST ?? '127.0.0.1';
const migrations = path.join(root, 'api', 'migrations');

await mkdir(dataDir, { recursive: true });
const db = await PGlite.create(dataDir);

await db.exec(`
  create table if not exists dev_schema_migrations (
    name text primary key,
    applied_at timestamptz not null default now()
  )
`);

const files = (await readdir(migrations)).filter((name) => name.endsWith('.sql')).sort();
for (const file of files) {
  const applied = await db.query('select 1 from dev_schema_migrations where name = $1', [
    file,
  ]);
  if (applied.rows.length > 0) continue;
  const sql = await readFile(path.join(migrations, file), 'utf8');
  // Each migration owns its BEGIN/COMMIT. Wrapping it in db.transaction()
  // nests transactions and can commit the outer block before the bookkeeping.
  await db.exec(sql);
  await db.query('insert into dev_schema_migrations (name) values ($1)', [file]);
  console.log(`applied ${file}`);
}

// `wrangler dev` reloads isolates and each one keeps its own small pool, so a
// low ceiling shows up as requests that wait forever for a connection.
const server = new PGLiteSocketServer({ db, port, host, maxConnections: 50 });
await server.start();
console.log(
  `DuckClean dev database on postgres://duckclean:duckclean@${host}:${port}/duckclean`,
);
console.log('PGlite accepts any user and password; the DSN only has to reach this port.');

let stopping = false;
async function stop() {
  if (stopping) return;
  stopping = true;
  await server.stop();
  await db.close();
  process.exit(0);
}
process.on('SIGINT', () => void stop());
process.on('SIGTERM', () => void stop());
