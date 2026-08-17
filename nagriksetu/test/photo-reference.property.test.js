// test/photo-reference.property.test.js
// Property-based tests for photo reference conditional persistence.
// Feature: nagriksetu-website, Property 4 (Task 5.3).
import test from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';

import { openDatabase } from '../src/db.js';
import { createComplaint, getComplaintById } from '../src/complaints.js';
import { ALLOWED_CATEGORIES } from '../src/validation.js';

// A generator for a non-empty, non-whitespace string value.
const nonBlank = fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0);

// A generator for a valid complaint submission whose photoReference is either
// provided (a genuine non-empty value) or absent (undefined).
const submissionWithOptionalPhoto = fc.record({
  citizenName: nonBlank,
  category: fc.constantFrom(...ALLOWED_CATEGORIES),
  locationArea: nonBlank,
  description: nonBlank,
  contact: fc.option(nonBlank, { nil: undefined }),
  photoReference: fc.option(nonBlank, { nil: undefined }),
});

test(
  'Feature: nagriksetu-website, Property 4: Photo reference conditional persistence — the persisted record has a non-empty photoReference iff one was provided',
  () => {
    fc.assert(
      fc.property(submissionWithOptionalPhoto, (submission) => {
        // Fresh in-memory database per iteration for isolation.
        const db = openDatabase(':memory:');
        try {
          const complaintId = createComplaint(submission, db);
          const record = getComplaintById(complaintId, db);

          assert.ok(record, 'expected the created complaint to be retrievable');

          const providedPhoto =
            typeof submission.photoReference === 'string' &&
            submission.photoReference.trim().length > 0;

          const persistedPhoto =
            typeof record.photoReference === 'string' &&
            record.photoReference.trim().length > 0;

          // Biconditional: persisted iff provided.
          assert.equal(
            persistedPhoto,
            providedPhoto,
            `photoReference persistence mismatch: provided=${providedPhoto}, persisted=${JSON.stringify(record.photoReference)}`
          );

          // When provided, the stored value must equal the submitted value.
          if (providedPhoto) {
            assert.equal(record.photoReference, submission.photoReference);
          } else {
            assert.equal(record.photoReference, null);
          }
        } finally {
          db.close();
        }
      }),
      { numRuns: 100 }
    );
  }
);
