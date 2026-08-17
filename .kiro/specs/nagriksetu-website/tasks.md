# Implementation Plan: NagrikSetu Website

## Overview

This plan builds NagrikSetu as a self-contained Node.js + Express + SQLite application with a vanilla frontend. Work proceeds bottom-up: project scaffolding first, then the backend building blocks (database, ID generation, validation, data-access), then the HTTP server that wires them together, then the five defect-free frontend pages plus the shared stylesheet and ES-module client script. Property-based tests (validating the 11 correctness properties) and example/unit tests are placed close to the code they exercise so regressions surface early. All tests run against an in-memory/temporary SQLite database.

## Tasks

- [ ] 1. Scaffold the NagrikSetu project
  - [x] 1.1 Create the project structure and manifest
    - Create the `nagriksetu/` project directory structure: `src/`, `public/`, `uploads/`, `data/`.
    - Create `package.json` with the project manifest, `type: "module"` (for ES module server code), a `start` script running `node server.js`, and a `test` script.
    - Add dependencies (`express`, `better-sqlite3` or equivalent, `multer`) and the chosen property-based testing library (e.g., `fast-check`) plus a test runner.
    - _Requirements: 5.1, 5.2_

- [ ] 2. Implement the database layer
  - [x] 2.1 Create `src/db.js` with schema initialization
    - Open (creating if absent) the SQLite database file under `data/`.
    - Create the `complaints` table if it does not exist with all columns: `id`, `complaint_id`, `year`, `sequence`, `citizen_name`, `category`, `location_area`, `description`, `contact`, `photo_reference`, `status`, `created_at`, `updated_at`.
    - Add constraints: `UNIQUE(complaint_id)`, `UNIQUE(year, sequence)`, `CHECK` on `category` (five allowed values) and `status` (three allowed values), `DEFAULT 'Pending'` on `status`.
    - Support an in-memory/temporary database path for tests, and export the shared connection handle.
    - _Requirements: 5.3, 5.4_

- [ ] 3. Implement Complaint_ID generation
  - [x] 3.1 Create `src/complaintId.js`
    - Implement `generateComplaintId(db, now)` producing `NGP-<four-digit-year>-<zero-padded-sequence>`.
    - Derive the sequence from `SELECT COALESCE(MAX(sequence),0) FROM complaints WHERE year = :year` plus one; zero-pad to at least four digits and allow natural growth beyond 9999.
    - _Requirements: 1.4, 5.4_

- [ ] 4. Implement submission validation
  - [x] 4.1 Create `src/validation.js`
    - Implement `validateSubmission(input)` returning `{ valid, errors }` where `errors` lists missing required fields (citizen name, category, location area, description).
    - Reject a `category` that is not one of Pothole, Garbage, Water, Traffic, Other.
    - _Requirements: 1.2, 1.9_

  - [ ]* 4.2 Write property test for incomplete-submission rejection
    - **Property 5: Incomplete submissions are rejected without persistence**
    - **Validates: Requirements 1.9**

- [ ] 5. Implement the data-access layer
  - [x] 5.1 Create `src/complaints.js`
    - Implement `createComplaint(input)`: within a single transaction, call `generateComplaintId`, insert the record with `status = 'Pending'` and ISO 8601 `created_at`/`updated_at`, persist `photo_reference` when a photo was attached, and return the generated Complaint_ID. Roll back on any failure.
    - Implement `getComplaintById(id)`: return the matching record mapped to the API/domain shape, or `null`.
    - _Requirements: 1.3, 1.5, 1.6, 1.11, 5.3, 5.5_

  - [ ]* 5.2 Write property test for creation invariants
    - **Property 3: Creation invariants — pending status and valid timestamps**
    - **Validates: Requirements 1.5, 1.6**

  - [ ]* 5.3 Write property test for photo reference conditional persistence
    - **Property 4: Photo reference conditional persistence**
    - **Validates: Requirements 1.11**

- [ ] 6. Implement the Express server and REST endpoints
  - [x] 6.1 Create `server.js` with static serving and app wiring
    - Create the Express app, register `express.static('public')` and photo serving from `uploads/`, and listen on a configurable port (default 3000).
    - Wire `src/db.js`, `src/complaints.js`, `src/validation.js`, and `src/complaintId.js` together.
    - _Requirements: 4.4, 5.1, 5.2_

  - [x] 6.2 Implement `POST /api/complaints`
    - Accept `multipart/form-data` (via multer for the optional photo) and `application/json`.
    - Run `validateSubmission`; on failure return `400` with `missingFields` and create no record; on success create the complaint and return `201` with `{ complaintId, status }`.
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.9, 1.11, 5.1, 5.3_

  - [x] 6.3 Implement `GET /api/complaints/:id`
    - Return `200` with the complaint's category, location area, description, status, and creation timestamp when found; return `404` not-found JSON when no match.
    - _Requirements: 2.2, 2.4, 5.2, 5.5_

  - [x] 6.4 Add the terminal 404 handler and JSON error handler
    - Return `404` JSON for any undefined route and a generic `500` JSON on unexpected errors.
    - _Requirements: 5.6_

  - [ ]* 6.5 Write property test for the submission-then-tracking round trip
    - **Property 1: Submission-then-tracking round trip**
    - **Validates: Requirements 1.3, 1.7, 2.2, 5.1, 5.2, 5.3**

  - [ ]* 6.6 Write property test for well-formed and unique Complaint_IDs
    - **Property 2: Complaint IDs are well-formed and unique**
    - **Validates: Requirements 1.4, 5.4**

  - [ ]* 6.7 Write property test for unknown-ID not-found behavior
    - **Property 6: Unknown Complaint_ID returns not-found**
    - **Validates: Requirements 2.4**

  - [ ]* 6.8 Write property test for lookup consistency (read idempotence)
    - **Property 7: Lookup consistency (read idempotence)**
    - **Validates: Requirements 5.5**

  - [ ]* 6.9 Write property test for undefined-route not-found behavior
    - **Property 8: Undefined routes return not-found**
    - **Validates: Requirements 5.6**

- [ ] 7. Checkpoint - backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Author the shared stylesheet
  - [x] 8.1 Create `public/style.css`
    - Define consistent presentation across all pages with correctly spelled class names, replacing defective identifiers such as `staus-section` and `satus progress` with `status-section` and `status-progress`.
    - Ensure every class referenced by the HTML pages has a matching selector.
    - _Requirements: 4.4, 6.3, 6.4_

- [ ] 9. Author the frontend pages (defect-free HTML)
  - [x] 9.1 Create `public/index.html` (Home_Page)
    - Introduce NagrikSetu; include navigation links to Report, Track, Dashboard, and About; link the shared stylesheet.
    - Ensure well-formed header tags and corrected spelling (no "placeholdeer").
    - _Requirements: 4.1, 4.3, 4.4, 6.1, 6.2_

  - [x] 9.2 Create `public/report.html` (Report_Page)
    - Provide a form with citizen name, category, location area, description, optional contact, and optional photo upload; category as a `<select>` limited to the five categories.
    - Include an area to display the returned Complaint_ID or validation messages; nav links; shared stylesheet; `<script type="module" src="script.js">`.
    - Ensure well-formed header tags and corrected spelling.
    - _Requirements: 1.1, 1.2, 1.8, 1.10, 4.3, 4.4, 6.1, 6.2_

  - [x] 9.3 Create `public/track.html` (Track_Page)
    - Provide a Complaint_ID input and lookup control, plus a results/message area; nav links; shared stylesheet; `<script type="module" src="script.js">`.
    - Ensure well-formed header tags and corrected spelling.
    - _Requirements: 2.1, 2.3, 2.5, 2.6, 4.3, 4.4, 6.1, 6.2_

  - [x] 9.4 Create `public/dashboard.html` (Dashboard_Page)
    - Display static demonstration counts by category (Pothole, Garbage, Water, Traffic, Other) and by status (Pending, In Progress, Resolved); nav links; shared stylesheet.
    - Use the corrected `status-section`/`status-progress` class names; ensure well-formed header tags.
    - _Requirements: 3.1, 3.2, 4.3, 4.4, 6.1, 6.3_

  - [x] 9.5 Create `public/about.html` (About_Page)
    - Present the mission and a description of how NagrikSetu helps citizens; nav links; shared stylesheet.
    - Ensure well-formed header tags and corrected spelling.
    - _Requirements: 4.2, 4.3, 4.4, 6.1, 6.2_

  - [ ]* 9.6 Write unit tests for static page content
    - Assert form field and category-option presence, dashboard demo values, mission text, and absence of the "placeholdeer" misspelling and defective class names.
    - _Requirements: 1.1, 1.2, 3.1, 3.2, 4.1, 4.2, 6.2_

- [ ] 10. Implement the client ES module
  - [x] 10.1 Create `public/script.js`
    - Detect the current page and wire handlers.
    - Report handler: prevent default submit, perform client-side required-field checks with a message identifying the missing input, send the request, and on success display the returned Complaint_ID.
    - Track handler: guard against empty/whitespace Complaint_ID (show a prompt, send no request); otherwise fetch and render details or the no-match message.
    - _Requirements: 1.8, 1.10, 2.3, 2.5, 2.6_

  - [ ]* 10.2 Write unit tests for client DOM rendering
    - Test report success/validation rendering and track details/not-found/empty-input handling against mocked responses.
    - _Requirements: 1.8, 1.10, 2.3, 2.5, 2.6_

- [ ] 11. Cross-page structural property tests
  - [ ]* 11.1 Write property test for navigation and stylesheet completeness
    - **Property 9: Navigation and stylesheet completeness across all pages**
    - **Validates: Requirements 4.3, 4.4**

  - [ ]* 11.2 Write property test for well-formed header tags
    - **Property 10: Header tags are well-formed across all pages**
    - **Validates: Requirements 6.1**

  - [ ]* 11.3 Write property test for HTML class references resolving in the stylesheet
    - **Property 11: All HTML class references resolve in the stylesheet**
    - **Validates: Requirements 6.4**

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP.
- Each task references specific requirements for traceability.
- Checkpoints ensure incremental validation of the backend and the full stack.
- Property tests validate the 11 universal correctness properties from the design; each runs a minimum of 100 iterations against an in-memory/temporary SQLite database and is tagged `Feature: nagriksetu-website, Property {number}`.
- Unit/example tests validate static page content and client DOM rendering.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1", "8.1"] },
    { "id": 2, "tasks": ["4.2", "5.1", "9.1", "9.2", "9.3", "9.4", "9.5"] },
    { "id": 3, "tasks": ["5.2", "5.3", "6.1", "9.6", "10.1", "11.1", "11.2", "11.3"] },
    { "id": 4, "tasks": ["6.2", "6.3", "6.4", "10.2"] },
    { "id": 5, "tasks": ["6.5", "6.6", "6.7", "6.8", "6.9"] }
  ]
}
```
