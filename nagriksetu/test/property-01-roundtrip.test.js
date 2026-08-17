// Feature: nagriksetu-website
//
// Property 1: Submission-then-tracking round trip
// Validates: Requirements 1.3, 1.7, 2.2, 5.1, 5.2, 5.3
//
// Integration-level property test. It exercises the real Express HTTP stack
// (POST /api/complaints, then GET /api/complaints/:id) against an isolated
// temporary SQLite database so the shared on-disk data/ DB is never touched.
//
// Isolation strategy: set NAGRIKSETU_DB_PATH to a unique temp file BEFORE the
// dynamic import of server.js (which transitively opens the DB at import time),
// then start the app on an ephemeral port (app.listen(0)) and drive it with the
// global fetch(). The server is closed and the temp DB removed on teardown.

import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { rmSync } from 'node:fs';
import fc from 'fast-check';

const DB_PATH = join(tmpdir(), `nagriksetu-p1-${randomUUID()}.db`);
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

// ---------------------------------------------------------------------------
// Generators for a valid complaint submission.
// ---------------------------------------------------------------------------
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

test('Feature: nagriksetu-website, Property 1: Submission-then-tracking round trip', async () => {
  await fc.assert(
    fc.asyncProperty(validSubmission, async (submission) => {
      // Submit the complaint.
      const postRes = await submit(submission);
      assert.equal(postRes.status, 201);
      const { complaintId, status } = await postRes.json();
      assert.equal(status, 'Pending');
      assert.match(complaintId, /^NGP-\d{4}-\d{4,}$/);

      // Look it up by the returned Complaint_ID.
      const getRes = await fetch(
        `${BASE}/api/complaints/${encodeURIComponent(complaintId)}`,
      );
      assert.equal(getRes.status, 200);
      const body = await getRes.json();

      // The looked-up record matches the submission and is Pending, and the
      // Complaint_ID in the lookup equals the one returned at submission.
      assert.equal(body.complaintId, complaintId);
      assert.equal(body.category, submission.category);
      assert.equal(body.locationArea, submission.locationArea);
      assert.equal(body.description, submission.description);
      assert.equal(body.status, 'Pending');
    }),
    { numRuns: 100 },
  );
});
