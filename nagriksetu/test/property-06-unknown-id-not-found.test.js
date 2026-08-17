// Feature: nagriksetu-website
//
// Property 6: Unknown Complaint_ID returns not-found
// Validates: Requirements 2.4
//
// For any Complaint_ID that does not correspond to a persisted complaint, a
// tracking lookup returns 404. A few real complaints are seeded first so the
// property meaningfully excludes persisted IDs via a precondition.
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

const DB_PATH = join(tmpdir(), `nagriksetu-p6-${randomUUID()}.db`);
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

async function submit(payload) {
  return fetch(`${BASE}/api/complaints`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

const arbitraryId = fc
  .string({ minLength: 1, maxLength: 40 })
  .filter((s) => s.trim().length > 0);

test('Feature: nagriksetu-website, Property 6: Unknown Complaint_ID returns not-found', async () => {
  // Seed a few genuine complaints so persisted IDs are excluded, not absent.
  const persisted = new Set();
  for (let i = 0; i < 3; i += 1) {
    const res = await submit({
      citizenName: 'Seed Citizen',
      category: 'Pothole',
      locationArea: 'Seed Area',
      description: `Seed complaint ${i}`,
    });
    assert.equal(res.status, 201);
    const { complaintId } = await res.json();
    persisted.add(complaintId);
  }

  await fc.assert(
    fc.asyncProperty(arbitraryId, async (id) => {
      // Only consider IDs that are genuinely not persisted.
      fc.pre(!persisted.has(id));

      const res = await fetch(`${BASE}/api/complaints/${encodeURIComponent(id)}`);
      assert.equal(res.status, 404);
      const body = await res.json();
      assert.equal(body.error, 'NotFound');
    }),
    { numRuns: 100 },
  );
});
