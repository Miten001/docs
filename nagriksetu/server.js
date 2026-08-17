// server.js — Express application entry point for NagrikSetu.
//
// Responsibilities:
//   - Create the Express app and serve the static frontend from public/.
//   - Serve stored complaint photos from uploads/.
//   - POST /api/complaints  — submit a complaint (JSON or multipart/form-data).
//   - GET  /api/complaints/:id — track a complaint by its Complaint_ID.
//   - Terminal 404 handler for undefined routes + JSON error handler.
//
// The app is exported so tests can import it without starting a listener;
// app.listen() is only invoked when this file is run directly.
//
// Requirements: 1.3–1.7, 1.9, 1.11, 2.2, 2.4, 4.4, 5.1, 5.2, 5.3, 5.5, 5.6

import express from 'express';
import multer from 'multer';
import { dirname, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';

import { createComplaint, getComplaintById } from './src/complaints.js';
import { validateSubmission } from './src/validation.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

const PUBLIC_DIR = resolve(__dirname, 'public');
const UPLOADS_DIR = resolve(__dirname, 'uploads');

// Ensure the uploads directory exists before multer tries to write into it.
mkdirSync(UPLOADS_DIR, { recursive: true });

/**
 * Human-readable labels for required fields, used to build validation
 * messages that identify the missing input.
 */
const FIELD_LABELS = {
  citizenName: 'Citizen name',
  category: 'Category',
  locationArea: 'Location area',
  description: 'Description',
};

/**
 * Build a human-readable validation message naming the offending field(s).
 * @param {string[]} missingFields
 * @returns {string}
 */
function buildValidationMessage(missingFields) {
  if (!missingFields || missingFields.length === 0) {
    return 'The submission is invalid.';
  }

  if (missingFields.length === 1) {
    const field = missingFields[0];
    const label = FIELD_LABELS[field] ?? field;
    // `category` may be flagged because it is missing or out of the allowed set.
    if (field === 'category') {
      return 'Category is required and must be one of the allowed values.';
    }
    return `${label} is required.`;
  }

  const labels = missingFields.map((field) => FIELD_LABELS[field] ?? field);
  return `The following fields are required: ${labels.join(', ')}.`;
}

// ---------------------------------------------------------------------------
// Multer configuration — store optional photo uploads on disk under uploads/.
// ---------------------------------------------------------------------------
const storage = multer.diskStorage({
  destination(_req, _file, cb) {
    cb(null, UPLOADS_DIR);
  },
  filename(_req, file, cb) {
    const unique = `${Date.now()}-${Math.round(Math.random() * 1e9)}`;
    cb(null, `photo-${unique}${extname(file.originalname) || ''}`);
  },
});

const upload = multer({ storage });

/**
 * Create and configure the Express application.
 * @returns {import('express').Express}
 */
export function createApp() {
  const app = express();

  // Parse JSON and urlencoded bodies (multipart is handled per-route by multer).
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));

  // Serve the static frontend (Home, Report, Track, Dashboard, About + assets).
  app.use(express.static(PUBLIC_DIR));

  // Serve stored complaint photos. photo_reference values point here.
  app.use('/uploads', express.static(UPLOADS_DIR));

  // -----------------------------------------------------------------------
  // POST /api/complaints — submit a complaint (Requirements 1.3–1.7, 1.9,
  // 1.11, 5.1, 5.3). Accepts multipart/form-data (optional "photo" file) and
  // application/json.
  // -----------------------------------------------------------------------
  app.post('/api/complaints', upload.single('photo'), (req, res, next) => {
    try {
      const body = req.body ?? {};

      const submission = {
        citizenName: body.citizenName,
        category: body.category,
        locationArea: body.locationArea,
        description: body.description,
        contact: body.contact,
      };

      const { valid, errors } = validateSubmission(submission);

      if (!valid) {
        // Validation failure: create no record (Requirement 1.9).
        return res.status(400).json({
          error: 'ValidationError',
          missingFields: errors,
          message: buildValidationMessage(errors),
        });
      }

      // Persist the stored filename as photo_reference when a photo was
      // uploaded (Requirement 1.11).
      if (req.file) {
        submission.photoReference = req.file.filename;
      }

      const complaintId = createComplaint(submission);

      // Success (Requirement 1.7): return the assigned Complaint_ID and status.
      return res.status(201).json({ complaintId, status: 'Pending' });
    } catch (err) {
      return next(err);
    }
  });

  // -----------------------------------------------------------------------
  // GET /api/complaints/:id — track a complaint (Requirements 2.2, 2.4, 5.2,
  // 5.5).
  // -----------------------------------------------------------------------
  app.get('/api/complaints/:id', (req, res, next) => {
    try {
      const complaint = getComplaintById(req.params.id);

      if (!complaint) {
        // Not found (Requirement 2.4).
        return res.status(404).json({
          error: 'NotFound',
          message: 'No complaint matches the entered Complaint ID.',
        });
      }

      // Return the tracking view (Requirement 2.2).
      return res.status(200).json({
        complaintId: complaint.complaintId,
        category: complaint.category,
        locationArea: complaint.locationArea,
        description: complaint.description,
        status: complaint.status,
        createdAt: complaint.createdAt,
      });
    } catch (err) {
      return next(err);
    }
  });

  // -----------------------------------------------------------------------
  // Terminal 404 handler for undefined routes (Requirement 5.6).
  // -----------------------------------------------------------------------
  app.use((_req, res) => {
    res.status(404).json({ error: 'NotFound' });
  });

  // -----------------------------------------------------------------------
  // JSON error handler — generic 500 on unexpected errors (Requirement 5.6).
  // -----------------------------------------------------------------------
  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    // Avoid leaking internal details; return a generic message.
    res.status(500).json({ error: 'InternalServerError' });
  });

  return app;
}

// Shared application instance (used by tests and by the direct-run listener).
const app = createApp();

// Only start listening when this file is executed directly (not when imported).
const isRunDirectly =
  process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isRunDirectly) {
  const PORT = process.env.PORT || 3000;
  app.listen(PORT, () => {
    // eslint-disable-next-line no-console
    console.log(`NagrikSetu server listening on http://localhost:${PORT}`);
  });
}

export { app };
export default app;
