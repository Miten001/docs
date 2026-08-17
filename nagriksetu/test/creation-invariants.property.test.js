// test/creation-invariants.property.test.js
// Property-based tests for complaint creation invariants.
// Feature: nagriksetu-website, Property 3 (Task 5.2).
import test from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';

import { openDatabase } from '../src/db.js';
import { createComplaint, getComplaintById } from '../src/complaints.js';
import { ALLOWED_CATEGORIES } from '../src/validation.js';

// A generator for a non-empty, non-whitespace string value.
const nonBlank = fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0);

// A generator for a valid complaint submission.
const validSubmission = fc.record({
  citizenName: nonBlank,
  category: fc.constantFrom(...ALLOWED_CATEGORIES),
  locationArea: nonBlank,
  description: nonBlank,
  contact: fc.option(nonBlank, { nil: undefined }),
});

test(
  'Feature: nagriksetu-website, Property 3: Creation invariants — pending status and valid timestamps',
  () => {
    fc.assert(
      fc.property(validSubmission, (submission) => {
        // Fresh in-memory database per iteration for isolation.
        const db = openDatabase(':memory:');
        try {
          const complaintId = createComplaint(submission, db);
          const record = getComplaintById(complaintId, db);

          assert.ok(record, 'expected the created complaint to be retrievable');

          // Status must be Pending on creation.
          assert.equal(record.status, 'Pending');

          // Both timestamps must be present.
          assert.ok(record.createdAt, 'expected a creation timestamp');
          assert.ok(record.updatedAt, 'expected a last-updated timestamp');

          // Timestamps must be valid dates.
          const created = new Date(record.createdAt).getTime();
          const updated = new Date(record.updatedAt).getTime();
          assert.ok(!Number.isNaN(created), 'createdAt must be a valid timestamp');
          assert.ok(!Number.isNaN(updated), 'updatedAt must be a valid timestamp');

          // Creation timestamp must not be later than last-updated timestamp.
          assert.ok(
            created <= updated,
            `expected createdAt (${record.createdAt}) <= updatedAt (${record.updatedAt})`
          );
        } finally {
          db.close();
        }
      }),
      { numRuns: 100 }
    );
  }
);
