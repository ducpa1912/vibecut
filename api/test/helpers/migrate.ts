import { readFileSync } from 'node:fs';
import type { PGlite } from '@electric-sql/pglite';

/** Applies every migration in order to one PGlite instance. */
export const MIGRATIONS = ['0001_init.sql', '0002_m1.sql', '0003_m2.sql'];

export async function migrate(db: PGlite): Promise<void> {
  for (const file of MIGRATIONS) {
    const sql = readFileSync(`migrations/${file}`, 'utf8');
    await db.exec(sql);
  }
}
