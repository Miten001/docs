// Feature: nagriksetu-website
//
// Property 2: Complaint IDs are well-formed and unique
// Validates: Requirements 1.4, 5.4
//
// For any sequence of valid submissions, every returned Complaint_ID matches
// NGP-<four-digit-year>-<sequence> and no two submissions share an ID.
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

const DB_PATH = join(tmpdir(), `nagriksetu-p2-${randomUUID()}.db`);
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
  .string({ minLength: 1, maxLength: 120 })
  .filter((s) => s.trim().length > 0);

const category = fc.constantFrom('Pothole', 'Garbage', 'Water', 'Traffic', 'Other');

const validSubmission = fc.record({
  citizenName: nonBlank,
  category,
  locationArea: nonBlank,
  description: nonBlank,
});

const submissionBatch = fc.array(validSubmission, { minLength: 1, maxLength: 6 });

async function submit(payload) {
  return fetch(`${BASE}/api/complaints`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

test('Feature: nagriksetu-website, Property 2: Complaint IDs are well-formed and unique', async () => {
  // Uniqueness is tracked across every submission made during the whole run.
  const seen = new Set();
  const currentYear = String(new Date().getFullYear());
  const idPattern = /^NGP-(\d{4})-(\d{4,})$/;

  await fc.assert(
    fc.asyncProperty(submissionBatch, async (batch) => {
      for (const submission of batch) {
        const res = await submit(submission);
        assert.equal(res.status, 201);
        const { complaintId } = await res.json();

        // Well-formed: NGP-<four-digit-year>-<sequence>.
        const match = idPattern.exec(complaintId);
        assert.ok(match, `id "${complaintId}" is malformed`);
        assert.equal(match[1], currentYear);

        // Unique across all submissions.
        assert.ok(!seen.has(complaintId), `duplicate Complaint_ID: ${complaintId}`);
        seen.add(complaintId);
      }
    }),
    { numRuns: 100 },
  );
});
