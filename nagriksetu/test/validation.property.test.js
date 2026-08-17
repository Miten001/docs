// test/validation.property.test.js
// Property-based tests for submission validation.
// Feature: nagriksetu-website, Property 5 (Task 4.2).
import test from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';

import { validateSubmission, ALLOWED_CATEGORIES } from '../src/validation.js';

// The four required submission fields.
const REQUIRED_FIELDS = ['citizenName', 'category', 'locationArea', 'description'];

// A generator for a "present" (non-empty, non-whitespace) string value.
const nonBlank = fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0);

// How a missing field can be represented: omitted (undefined) or blank/whitespace.
const missingValue = fc.constantFrom(undefined, '', '   ', '\t', '\n  ');

test(
  'Feature: nagriksetu-website, Property 5: Incomplete submissions are rejected without persistence — validateSubmission returns valid:false with the missing required field(s) in errors',
  () => {
    fc.assert(
      fc.property(
        // A mask marking which required fields are missing (at least one is).
        fc
          .record({
            citizenName: fc.boolean(),
            category: fc.boolean(),
            locationArea: fc.boolean(),
            description: fc.boolean(),
          })
          .filter((mask) => REQUIRED_FIELDS.some((f) => mask[f])),
        // Present values used for the fields that are NOT missing.
        fc.record({
          citizenName: nonBlank,
          // Present category uses an allowed value so it does not trigger an
          // additional "invalid category" error unrelated to this property.
          category: fc.constantFrom(...ALLOWED_CATEGORIES),
          locationArea: nonBlank,
          description: nonBlank,
        }),
        // Values used to represent each missing field.
        fc.record({
          citizenName: missingValue,
          category: missingValue,
          locationArea: missingValue,
          description: missingValue,
        }),
        (mask, present, missing) => {
          const input = {};
          const expectedMissing = [];
          for (const field of REQUIRED_FIELDS) {
            if (mask[field]) {
              expectedMissing.push(field);
              // Only assign when it is a blank string; leave omitted for undefined.
              if (missing[field] !== undefined) {
                input[field] = missing[field];
              }
            } else {
              input[field] = present[field];
            }
          }

          const result = validateSubmission(input);

          // The submission must be rejected.
          assert.equal(result.valid, false);
          // Every missing required field must be reported in errors.
          for (const field of expectedMissing) {
            assert.ok(
              result.errors.includes(field),
              `expected errors to include missing field "${field}", got ${JSON.stringify(result.errors)}`
            );
          }
        }
      ),
      { numRuns: 200 }
    );
  }
);
