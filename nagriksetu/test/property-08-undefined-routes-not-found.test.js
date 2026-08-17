// Feature: nagriksetu-website
//
// Property 8: Undefined routes return not-found
// Validates: Requirements 5.6
//
// For any request path matching neither a static asset nor a defined API route,
// the server returns 404. Generated paths are namespaced under a unique
// "undefined-<uuid>" prefix so they can never collide with a real static file
// (index.html, style.css, ...) or the defined API routes.
//
// Isolation: NAGRIKSETU_DB_PATH is pointed at a unique temp DB before importing
// server.js; the app runs on an ephemeral port and is driven with fetch().

import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { rmSync } from 'node:fs';
import fc from 'fast-check';

const DB_PATH = join(tmpdir(), `nagriksetu-p8-${randomUUID()}.db`);
process.env.NAGRIKSETU_DB_PATH = DB_PATH;

const { app } = await import('../server.js');

const server = app.listen(0);
await once(server, 'listening');
const { port } = server.address();
const BASE = `http://127.0.0.1:${port}`;

after(async () => {
  await new Promise((resolve) => server.close(resolve));
  for (const suffix of ['', '-wal', '-shm']) {
    try {
      rmSync(DB_PATH + suffix, { force: true });
    } catch {
      /* best-effort cleanup */
    }
  }
});

const method = fc.constantFrom('GET', 'PUT', 'DELETE', 'PATCH', 'POST');

const pathSegments = fc.array(
  fc.string({ minLength: 1, maxLength: 12 }).filter((s) => s.trim().length > 0),
  { minLength: 0, maxLength: 4 },
);

test('Feature: nagriksetu-website, Property 8: Undefined routes return not-found', async () => {
  await fc.assert(
    fc.asyncProperty(method, pathSegments, async (httpMethod, segments) => {
      const encoded = segments.map(encodeURIComponent).join('/');
      // Unique prefix guarantees the path is neither a static asset nor a
      // defined API route.
      const path = `/undefined-${randomUUID()}${encoded ? `/${encoded}` : ''}`;

      const res = await fetch(`${BASE}${path}`, { method: httpMethod });
      assert.equal(res.status, 404);
      const body = await res.json();
      assert.equal(body.error, 'NotFound');
    }),
    { numRuns: 100 },
  );
});
