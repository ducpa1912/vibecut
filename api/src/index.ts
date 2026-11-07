import { createApp } from './app';
import type { Bindings } from './bindings';
import { createQueueHandler } from './jobs';
import { runtimeFor } from './runtime';

/**
 * DuckClean API Worker.
 *
 * Video bytes never pass through this Worker: it signs R2 URLs, writes metadata
 * and job state, dispatches signed worker calls and meters usage.
 */
const app = createApp(runtimeFor);
const queue = createQueueHandler(runtimeFor);

export default {
  fetch: app.fetch,
  queue,
} satisfies ExportedHandler<Bindings>;

export type { Bindings };
