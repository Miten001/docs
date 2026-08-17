// Feature: nagriksetu-website
//
// Property 7: Lookup consistency (read idempotence)
// Validates: Requirements 5.5
//
// For any persisted complaint, repeated tracking lookups by its Complaint_ID
// return identical complaint data every time.
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

const DB_PATH = join(tmpdir(), `nagriksetu-p7-${randomUUID()}.db`);
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

const nonBlank = fc
  .string({ minLength: 1, maxLength: 200 })
  .filter((s) => s.trim().length > 0);

const category = fc.constantFrom('Pothole', 'Garbage', 'Water', 'Traffic', 'Other');

const validSubmission = fc.record({
  citizenName: nonBlank,
  category,
  locationArea: nonBlank,
  description: nonBlank,
});

async function submit(payload) {
  return fetch(`${BASE}/api/complaints`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

test('Feature: nagriksetu-website, Property 7: Lookup consistency (read idempotence)', async () => {
  await fc.assert(
    fc.asyncProperty(
      validSubmission,
      fc.integer({ min: 2, max: 5 }),
      async (submission, repeats) => {
        // Persist the complaint.
        const postRes = await submit(submission);
        assert.equal(postRes.status, 201);
        const { complaintId } = await postRes.json();

        // Look it up several times and collect the serialized bodies.
        const bodies = [];
        for (let i = 0; i < repeats; i += 1) {
          const res = await fetch(
            `${BASE}/api/complaints/${encodeURIComponent(complaintId)}`,
          );
          assert.equal(res.status, 200);
          bodies.push(JSON.stringify(await res.json()));
        }

        // Every lookup returns identical data.
        for (const body of bodies) {
          assert.equal(body, bodies[0]);
        }
      },
    ),
    { numRuns: 100 },
  );
});
