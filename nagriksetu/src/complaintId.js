// src/complaintId.js — Complaint_ID generation (Requirements 1.4, 5.4)

/**
 * Return the four-digit year for a given Date.
 * @param {Date} now
 * @returns {number}
 */
function fourDigitYear(now) {
  return now.getFullYear();
}

/**
 * Zero-pad a non-negative integer to at least `width` digits.
 * Values requiring more than `width` digits grow naturally (e.g. beyond 9999).
 * @param {number} value
 * @param {number} width
 * @returns {string}
 */
function zeroPad(value, width) {
  return String(value).padStart(width, '0');
}

/**
 * Generate the next Complaint_ID of the form `NGP-<year>-<sequence>`.
 *
 * The sequence is scoped to the current year: it is one greater than the
 * maximum existing `sequence` for that year (COALESCE to 0 when none exist).
 * The caller is responsible for executing this together with the INSERT inside
 * a single transaction so concurrent submissions cannot collide.
 *
 * @param {import('better-sqlite3').Database} db The database handle.
 * @param {Date} now The reference time used to derive the year.
 * @returns {{ id: string, year: number, sequence: number }}
 */
export function generateComplaintId(db, now) {
  const year = fourDigitYear(now);

  const row = db
    .prepare('SELECT COALESCE(MAX(sequence), 0) AS maxSeq FROM complaints WHERE year = ?')
    .get(year);

  const nextSeq = row.maxSeq + 1;
  const id = `NGP-${year}-${zeroPad(nextSeq, 4)}`;

  return { id, year, sequence: nextSeq };
}

export default generateComplaintId;
