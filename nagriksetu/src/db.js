// src/db.js — SQLite connection + schema initialization (Requirements 5.3, 5.4)
import Database from 'better-sqlite3';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Default on-disk database location: <project>/data/nagriksetu.db
const DEFAULT_DB_PATH = resolve(__dirname, '..', 'data', 'nagriksetu.db');

/**
 * SQL that creates the `complaints` table (idempotent).
 * Column set, constraints, and CHECK value sets match the design's data model.
 */
const CREATE_COMPLAINTS_TABLE = `
CREATE TABLE IF NOT EXISTS complaints (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  complaint_id    TEXT    NOT NULL,
  year            INTEGER NOT NULL,
  sequence        INTEGER NOT NULL,
  citizen_name    TEXT    NOT NULL,
  category        TEXT    NOT NULL CHECK (category IN ('Pothole', 'Garbage', 'Water', 'Traffic', 'Other')),
  location_area   TEXT    NOT NULL,
  description     TEXT    NOT NULL,
  contact         TEXT,
  photo_reference TEXT,
  status          TEXT    NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'In Progress', 'Resolved')),
  created_at      TEXT    NOT NULL,
  updated_at      TEXT    NOT NULL,
  UNIQUE (complaint_id),
  UNIQUE (year, sequence)
);
`;

/**
 * Initialize the schema on a connection handle.
 * @param {import('better-sqlite3').Database} db
 * @returns {import('better-sqlite3').Database}
 */
export function initSchema(db) {
  db.exec(CREATE_COMPLAINTS_TABLE);
  return db;
}

/**
 * Open (creating if absent) a SQLite database and initialize the schema.
 *
 * @param {string} [dbPath] Path to the database file. Use ':memory:' for an
 *   in-memory database (used by tests). Defaults to <project>/data/nagriksetu.db.
 * @returns {import('better-sqlite3').Database} The initialized connection handle.
 */
export function openDatabase(dbPath = DEFAULT_DB_PATH) {
  // Ensure the parent directory exists for on-disk databases.
  if (dbPath !== ':memory:') {
    mkdirSync(dirname(dbPath), { recursive: true });
  }

  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');

  return initSchema(db);
}

// Shared, application-wide connection handle.
//
// The path can be overridden via the NAGRIKSETU_DB_PATH environment variable.
// This enables test isolation: a test process sets NAGRIKSETU_DB_PATH to a
// unique temporary file (or ':memory:') *before* importing this module (or
// server.js, which transitively imports it), so integration tests exercise
// the real HTTP stack without writing to the shared on-disk data/ database.
// When the variable is unset, the default on-disk location is used.
const db = openDatabase(process.env.NAGRIKSETU_DB_PATH || DEFAULT_DB_PATH);

export { DEFAULT_DB_PATH };
export default db;
