// src/validation.js — Submission field validation (Requirements 1.2, 1.9)

/** Allowed complaint categories. */
export const ALLOWED_CATEGORIES = ['Pothole', 'Garbage', 'Water', 'Traffic', 'Other'];

/**
 * Required submission fields, in the order errors should be reported.
 * Field names match the API/domain shape used by the client and server.
 */
const REQUIRED_FIELDS = ['citizenName', 'category', 'locationArea', 'description'];

/**
 * Treat a value as "present" only when it is a non-empty, non-whitespace string.
 * @param {unknown} value
 * @returns {boolean}
 */
function isPresent(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

/**
 * Validate a complaint submission.
 *
 * Reports every missing required field (citizenName, category, locationArea,
 * description). Additionally, when a category is provided but is not one of the
 * allowed values, `category` is reported as an error.
 *
 * @param {Record<string, unknown>} [input] The submission payload.
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateSubmission(input) {
  const data = input ?? {};
  const errors = [];

  for (const field of REQUIRED_FIELDS) {
    if (!isPresent(data[field])) {
      errors.push(field);
    }
  }

  // Reject a category that is present but outside the allowed set.
  // (When category is missing it is already reported above; avoid duplicates.)
  if (isPresent(data.category) && !ALLOWED_CATEGORIES.includes(data.category)) {
    errors.push('category');
  }

  return { valid: errors.length === 0, errors };
}

export default validateSubmission;
