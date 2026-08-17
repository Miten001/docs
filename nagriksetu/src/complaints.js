// src/complaints.js — Data-access layer: create + fetch complaints
// (Requirements 1.3, 1.5, 1.6, 1.11, 5.3, 5.5)
import sharedDb from './db.js';
import { generateComplaintId } from './complaintId.js';

/**
 * Treat a value as "present" only when it is a non-empty, non-whitespace
 * string. Used to decide whether optional fields (contact, photo reference)
 * are persisted or stored as NULL.
 * @param {unknown} value
 * @returns {boolean}
 */
function isPresent(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

/**
 * Map a raw `complaints` table row to the API/domain Complaint shape.
 * @param {Record<string, unknown>} row
 * @returns {{
 *   complaintId: string,
 *   citizenName: string,
 *   category: string,
 *   locationArea: string,
 *   description: string,
 *   contact: string | null,
 *   photoReference: string | null,
 *   status: string,
 *   createdAt: string,
 *   updatedAt: string
 * }}
 */
function mapRowToComplaint(row) {
  return {
    complaintId: row.complaint_id,
    citizenName: row.citizen_name,
    category: row.category,
    locationArea: row.location_area,
    description: row.description,
    contact: row.contact ?? null,
    photoReference: row.photo_reference ?? null,
    status: row.status,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

/**
 * Create a Complaint record.
 *
 * The Complaint_ID generation (which reads MAX(sequence) for the year) and the
 * INSERT run inside a single transaction, so concurrent submissions cannot
 * receive duplicate IDs. On any failure the transaction rolls back, leaving no
 * partial record.
 *
 * The record is created with `status = 'Pending'` and ISO 8601 `created_at` /
 * `updated_at` timestamps. A `photo_reference` is persisted only when a photo
 * was attached (otherwise NULL).
 *
 * @param {{
 *   citizenName: string,
 *   category: string,
 *   locationArea: string,
 *   description: string,
 *   contact?: string,
 *   photoReference?: string
 * }} input The validated submission payload.
 * @param {import('better-sqlite3').Database} [db] Optional connection handle
 *   (defaults to the shared application handle; tests may pass an in-memory db).
 * @returns {string} The generated Complaint_ID (e.g. "NGP-2024-0042").
 */
export function createComplaint(input, db = sharedDb) {
  const now = new Date();
  const timestamp = now.toISOString();

  const insertRecord = db.transaction((data) => {
    const { id, year, sequence } = generateComplaintId(db, now);

    db.prepare(
      `INSERT INTO complaints (
         complaint_id, year, sequence, citizen_name, category,
         location_area, description, contact, photo_reference,
         status, created_at, updated_at
       ) VALUES (
         @complaintId, @year, @sequence, @citizenName, @category,
         @locationArea, @description, @contact, @photoReference,
         'Pending', @createdAt, @updatedAt
       )`
    ).run({
      complaintId: id,
      year,
      sequence,
      citizenName: data.citizenName,
      category: data.category,
      locationArea: data.locationArea,
      description: data.description,
      contact: isPresent(data.contact) ? data.contact : null,
      photoReference: isPresent(data.photoReference) ? data.photoReference : null,
      createdAt: timestamp,
      updatedAt: timestamp,
    });

    return id;
  });

  return insertRecord(input);
}

/**
 * Fetch a Complaint by its Complaint_ID.
 *
 * @param {string} id The Complaint_ID to look up.
 * @param {import('better-sqlite3').Database} [db] Optional connection handle
 *   (defaults to the shared application handle).
 * @returns {ReturnType<typeof mapRowToComplaint> | null} The matching complaint
 *   mapped to the API/domain shape, or `null` when no record matches.
 */
export function getComplaintById(id, db = sharedDb) {
  const row = db
    .prepare('SELECT * FROM complaints WHERE complaint_id = ?')
    .get(id);

  return row ? mapRowToComplaint(row) : null;
}

export default { createComplaint, getComplaintById };
