import { Pool } from 'pg';
import type { QueryResultRow } from 'pg';

/**
 * The smallest database surface the routes use. Tests run the same SQL against
 * PGlite, so the contract is verified against real Postgres semantics without a
 * server; production uses a Hyperdrive-backed `pg` pool.
 */
export interface Sql {
  query<T extends QueryResultRow = QueryResultRow>(
    text: string,
    values?: readonly unknown[],
  ): Promise<{ rows: T[] }>;
  transaction<T>(fn: (tx: Sql) => Promise<T>): Promise<T>;
}

/** One pool per connection string per isolate, as Cloudflare recommends. */
const pools = new Map<string, Pool>();

function poolFor(connectionString: string): Pool {
  const existing = pools.get(connectionString);
  if (existing) return existing;
  const pool = new Pool({ connectionString, max: 5, idleTimeoutMillis: 5_000 });
  pools.set(connectionString, pool);
  return pool;
}

export function pgSql(connectionString: string): Sql {
  const pool = poolFor(connectionString);
  return {
    async query<T extends QueryResultRow>(text: string, values?: readonly unknown[]) {
      const result = await pool.query<T>(text, values ? [...values] : undefined);
      return { rows: result.rows };
    },
    async transaction<T>(fn: (tx: Sql) => Promise<T>) {
      const client = await pool.connect();
      try {
        await client.query('begin');
        const tx: Sql = {
          async query<U extends QueryResultRow>(
            text: string,
            values?: readonly unknown[],
          ) {
            const result = await client.query<U>(text, values ? [...values] : undefined);
            return { rows: result.rows };
          },
          transaction: async <U>(inner: (tx2: Sql) => Promise<U>) => inner(tx),
        };
        const value = await fn(tx);
        await client.query('commit');
        return value;
      } catch (error) {
        await client.query('rollback').catch(() => undefined);
        throw error;
      } finally {
        client.release();
      }
    },
  };
}

/** PGlite implements the same protocol; tests run the real SQL against it. */
interface PgliteLike {
  query<T>(text: string, values?: unknown[]): Promise<{ rows: T[] }>;
  transaction<T>(fn: (tx: PgliteLike) => Promise<T>): Promise<T>;
}

function adaptPglite(db: PgliteLike): Sql {
  return {
    async query<T extends QueryResultRow>(text: string, values?: readonly unknown[]) {
      const result = await db.query<T>(text, values ? [...values] : undefined);
      return { rows: result.rows };
    },
    async transaction<T>(fn: (tx: Sql) => Promise<T>) {
      return db.transaction(async (inner) => fn(adaptPglite(inner)));
    },
  };
}

export function pgliteSql(db: unknown): Sql {
  return adaptPglite(db as PgliteLike);
}
