# Design Document

## Overview

NagrikSetu is a civic engagement platform for the citizens of Nagpur. This design converts a set of static HTML pages into a functional website backed by a Node.js + Express REST API and a SQLite database. Citizens submit civic complaints through a form, receive a unique, human-readable Complaint ID (for example, `NGP-2024-0042`), and later use that ID to track the status and details of their complaint. A Civic Dashboard displays static demonstration statistics, and informational pages (Home, About) describe the platform.

The system is a self-contained standalone application that is independent of the surrounding `docs` repository. It is composed of two cooperating parts:

- **Frontend** — five static HTML pages, a shared stylesheet, and a single client-side ES module (`script.js`) served as static assets.
- **Backend_API** — an Express server that serves the static frontend, exposes two JSON REST endpoints (submit and track), generates Complaint IDs, and persists Complaint records in SQLite.

Design goals:

- Persist complaints in a shared SQLite database so all citizens see consistent data across devices (Requirement 5).
- Generate collision-free, human-readable Complaint IDs (Requirements 1.4, 5.4).
- Correct existing HTML defects — malformed header tags, the "placeholdeer" spelling error, and inconsistent CSS class names (Requirement 6).
- Keep the frontend framework-free (vanilla HTML/CSS/JS) with `script.js` authored as an ES module.

### Technology Stack

| Concern | Choice | Rationale |
| --- | --- | --- |
| Runtime | Node.js | Requested stack; ubiquitous, simple to run. |
| Web framework | Express | Minimal REST routing and static file serving. |
| Database | SQLite (via `better-sqlite3`) | Single-file, zero-config persistence; synchronous API simplifies ID sequencing. |
| File uploads | `multer` | Handles `multipart/form-data` for optional photo uploads. |
| Frontend | Vanilla HTML/CSS/JS | No framework; `script.js` is an ES module (`<script type="module">`). |

> Note: `better-sqlite3` and `multer` are the reference choices in this design. Implementation may substitute equivalent libraries (for example, `node:sqlite` or the async `sqlite3` driver) provided the behavior described here is preserved.

## Architecture

### Project Structure

The NagrikSetu application is created as a new self-contained project. All source files described below are created during implementation (they do not yet exist in the repository).

```
nagriksetu/
├── package.json                # Node project manifest and scripts
├── server.js                   # Express app entry point: routes, static serving, error handling
├── src/
│   ├── db.js                   # SQLite connection + schema initialization (migrations)
│   ├── complaintId.js          # Complaint_ID generation (NGP-<year>-<sequence>)
│   ├── complaints.js           # Data-access layer: create + fetch complaints
│   └── validation.js           # Submission field validation
├── public/                     # Static frontend assets served by Express
│   ├── index.html              # Home_Page
│   ├── report.html             # Report_Page (submission form)
│   ├── track.html              # Track_Page (lookup)
│   ├── dashboard.html          # Dashboard_Page (static demo stats)
│   ├── about.html              # About_Page
│   ├── style.css               # Shared stylesheet
│   └── script.js               # Client-side ES module (fetch calls + DOM logic)
├── uploads/                    # Stored photo files (photo references point here)
└── data/
    └── nagriksetu.db           # SQLite database file (created at first run)
```

> This structure is illustrative. The five HTML pages, `style.css`, and `script.js` correct the defects called out in Requirement 6 as they are authored (there is no legacy code to migrate in the repository; the "existing defects" are addressed in the newly authored pages so the delivered frontend is defect-free).

### Request Flow

```
Browser (HTML page + script.js ES module)
        │
        │  fetch() JSON / multipart
        ▼
Express server (server.js)
   ├── Static middleware ──────────► public/*.html, style.css, script.js
   ├── POST /api/complaints ───────► validation.js ─► complaintId.js ─► complaints.js ─► SQLite
   ├── GET  /api/complaints/:id ───► complaints.js ─► SQLite
   └── 404 handler (undefined routes)
```

1. The browser loads a static HTML page and its ES module `script.js`.
2. On the Report_Page, `script.js` collects form fields and `POST`s them to `/api/complaints`.
3. The server validates required fields, generates a Complaint_ID, persists the record, and returns the ID.
4. On the Track_Page, `script.js` `GET`s `/api/complaints/:id` and renders the returned details or a not-found message.

## Components and Interfaces

### Backend Components

#### `server.js` — Application Entry Point
- Creates the Express app.
- Registers `express.static('public')` to serve the frontend and `express.static('uploads')` (or a dedicated route) to serve stored photos.
- Mounts the complaint routes.
- Registers a terminal 404 handler for undefined routes (Requirement 5.6) and a JSON error handler.
- Listens on a configurable port (default `3000`).

#### `src/db.js` — Database Access
- Opens (and creates if absent) the SQLite database file.
- Runs schema initialization (create `complaints` table if it does not exist).
- Exports the shared connection handle.

#### `src/complaintId.js` — Complaint ID Generation
- Produces IDs of the form `NGP-<year>-<sequence>` where `<year>` is the four-digit current year and `<sequence>` is a zero-padded, monotonically increasing integer scoped to that year.
- Sequence derivation: query the maximum existing sequence for the current year and increment. The write of the new complaint and the sequence read occur within a single SQLite transaction so concurrent submissions cannot receive duplicate IDs (Requirements 1.4, 5.4).

#### `src/complaints.js` — Data-Access Layer
- `createComplaint(input)`: within a transaction, generates the Complaint_ID, inserts the record with `status = 'Pending'`, `created_at` and `updated_at` timestamps, and returns the generated ID.
- `getComplaintById(id)`: returns the matching record or `null`.

#### `src/validation.js` — Submission Validation
- `validateSubmission(input)`: returns a list of missing required fields (citizen name, category, location area, description). Also validates that `category` is one of the allowed values. Returns `{ valid, errors }`.

### REST API Interface

#### `POST /api/complaints` — Submit a Complaint (Requirements 1.3–1.7, 5.1, 5.3)

- **Request**: `multipart/form-data` (to support the optional photo) or `application/json` (when no photo).
  - `citizenName` (required, string)
  - `category` (required, one of `Pothole | Garbage | Water | Traffic | Other`)
  - `locationArea` (required, string)
  - `description` (required, string)
  - `contact` (optional, string)
  - `photo` (optional, file)
- **Success — `201 Created`**:
  ```json
  { "complaintId": "NGP-2024-0042", "status": "Pending" }
  ```
- **Validation failure — `400 Bad Request`** (Requirement 1.9): no record is created.
  ```json
  { "error": "ValidationError", "missingFields": ["locationArea"], "message": "Location area is required." }
  ```

#### `GET /api/complaints/:id` — Track a Complaint (Requirements 2.2, 5.2, 5.5)

- **Request**: path parameter `id` = Complaint_ID.
- **Success — `200 OK`**:
  ```json
  {
    "complaintId": "NGP-2024-0042",
    "category": "Pothole",
    "locationArea": "Dharampeth",
    "description": "Large pothole near the market",
    "status": "Pending",
    "createdAt": "2024-05-01T09:30:00.000Z"
  }
  ```
- **Not found — `404 Not Found`** (Requirement 2.4):
  ```json
  { "error": "NotFound", "message": "No complaint matches the entered Complaint ID." }
  ```

#### Undefined Routes (Requirement 5.6)
- Any request not matching a static asset or a defined API route returns `404 Not Found` with a JSON body `{ "error": "NotFound" }`.

### Frontend Components

#### Pages
All five pages share a common header/nav structure, link the shared stylesheet (`style.css`), and — where interactive — load `script.js` as an ES module: `<script type="module" src="script.js"></script>`.

| Page | File | Responsibility |
| --- | --- | --- |
| Home_Page | `index.html` | Introduce NagrikSetu; nav links to the other four pages (Req 4.1, 4.3). |
| Report_Page | `report.html` | Submission form with all fields; category `<select>` limited to the five categories; displays returned Complaint_ID or validation messages (Req 1.1, 1.2, 1.8, 1.10). |
| Track_Page | `track.html` | Complaint_ID input + lookup control; renders details, not-found, or empty-input prompt (Req 2.1, 2.3, 2.5, 2.6). |
| Dashboard_Page | `dashboard.html` | Static demonstration counts by category and by status (Req 3.1, 3.2). |
| About_Page | `about.html` | Mission and description of how NagrikSetu helps citizens (Req 4.2). |

#### `script.js` — Client Module (ES module)
Exposes page-aware behavior; detects the current page and wires the relevant handlers.

- **Report handler**: prevents default submit, performs client-side required-field checks, displays a validation message identifying the missing input (Req 1.10), sends the request, and on success displays the returned Complaint_ID (Req 1.8).
- **Track handler**: guards against an empty/whitespace Complaint_ID — if empty, shows a prompt and does not send the request (Req 2.6); otherwise fetches and renders details (Req 2.3) or the no-match message (Req 2.5).

#### `style.css` — Shared Stylesheet
- Provides consistent presentation across all pages (Req 4.4).
- Defines correctly spelled, consistent class names. The defective identifiers `staus-section` and `satus progress` are replaced with correctly spelled equivalents such as `status-section` and `status-progress`, and every class referenced by the HTML has a matching selector (Req 6.3, 6.4).

## Data Models

### `complaints` Table (SQLite)

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Internal row id. |
| `complaint_id` | TEXT | UNIQUE, NOT NULL | Human-readable `NGP-<year>-<sequence>` (Req 5.4). |
| `year` | INTEGER | NOT NULL | Year used for sequence scoping. |
| `sequence` | INTEGER | NOT NULL | Per-year sequence number. |
| `citizen_name` | TEXT | NOT NULL | Reporter name. |
| `category` | TEXT | NOT NULL, CHECK in allowed set | One of the five categories. |
| `location_area` | TEXT | NOT NULL | Area of the problem. |
| `description` | TEXT | NOT NULL | Problem description. |
| `contact` | TEXT | NULL | Optional contact. |
| `photo_reference` | TEXT | NULL | Optional stored file path/name (Req 1.11). |
| `status` | TEXT | NOT NULL, DEFAULT 'Pending' | One of `Pending | In Progress | Resolved` (Req 1.5). |
| `created_at` | TEXT | NOT NULL | ISO 8601 creation timestamp (Req 1.6). |
| `updated_at` | TEXT | NOT NULL | ISO 8601 last-updated timestamp (Req 1.6). |

Constraints and indexing:
- `UNIQUE(complaint_id)` enforces global ID uniqueness at the database layer as a defense-in-depth backstop to application sequencing (Req 5.4).
- `UNIQUE(year, sequence)` guarantees per-year sequence integrity.
- `CHECK` constraints restrict `category` and `status` to their allowed value sets.

### Complaint (API/domain shape)

```
Complaint {
  complaintId: string      // "NGP-2024-0042"
  citizenName: string
  category: "Pothole" | "Garbage" | "Water" | "Traffic" | "Other"
  locationArea: string
  description: string
  contact?: string
  photoReference?: string
  status: "Pending" | "In Progress" | "Resolved"
  createdAt: string        // ISO 8601
  updatedAt: string        // ISO 8601
}
```

### Complaint_ID Generation Algorithm

```
function generateComplaintId(db, now):
    year = fourDigitYear(now)
    // Executed inside the same transaction as the INSERT
    maxSeq = SELECT COALESCE(MAX(sequence), 0)
             FROM complaints WHERE year = :year
    nextSeq = maxSeq + 1
    id = "NGP-" + year + "-" + zeroPad(nextSeq, 4)
    return { id, year, sequence: nextSeq }
```

- The read of `MAX(sequence)` and the corresponding `INSERT` are wrapped in a single transaction, so two concurrent submissions cannot compute the same `nextSeq`. Combined with the `UNIQUE(year, sequence)` and `UNIQUE(complaint_id)` constraints, IDs are guaranteed distinct (Req 1.4, 5.4).
- `zeroPad(nextSeq, 4)` yields at least four digits (`0001`), and grows naturally beyond 9999.

## Error Handling

| Condition | Layer | Response / Behavior | Requirement |
| --- | --- | --- | --- |
| Missing required submission field | Backend | `400` with `missingFields`; no record inserted | 1.9 |
| Missing required field (client) | Frontend | Inline message naming the missing input; no request sent for known-empty required fields | 1.10 |
| Invalid `category` value | Backend | `400` validation error | 1.2, 1.9 |
| Track ID not found | Backend | `404` not-found JSON | 2.4 |
| Track not-found (client) | Frontend | "No complaint matches..." message | 2.5 |
| Empty Complaint_ID on Track | Frontend | Prompt to enter an ID; no request sent | 2.6 |
| Undefined route | Backend | `404` not-found JSON | 5.6 |
| Photo attached | Backend | Store file, persist `photo_reference` | 1.11 |
| Database/unexpected error | Backend | `500` with generic JSON error; no partial record (transaction rollback) | 5.3, 5.4 |

Transactional integrity: `createComplaint` performs ID sequencing and the insert in one transaction. On any failure the transaction rolls back, leaving no partial record and no consumed sequence gap that could later collide.

## Testing Strategy

A dual approach is used:

- **Property-based tests** validate universal behaviors of the backend across many generated inputs (submissions, IDs, lookups, error paths) and structural invariants across the frontend page set. Each property test runs a minimum of 100 iterations and is tagged `Feature: nagriksetu-website, Property {number}: {property_text}`. Backend property tests run against an in-memory/temporary SQLite database so 100+ iterations are cheap.
- **Example / unit tests** validate specific UI presence (form fields, category options, dashboard elements, navigation content), client DOM rendering given mocked responses, and the specific defect corrections (absence of "placeholdeer" and the misspelled class names).

Static-page checks (form field presence, category options, dashboard demo values, mission text, DOM rendering) are example-based because their behavior does not vary with input. Backend logic and cross-page structural invariants are property-based because behavior varies meaningfully with input and 100+ iterations surface edge cases (large text, special characters, many concurrent submissions, non-existent IDs, arbitrary undefined paths).

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Submission-then-tracking round trip

*For any* valid complaint submission (non-empty citizen name, allowed category, non-empty location area, non-empty description), submitting it and then looking it up by the returned Complaint_ID yields a record whose category, location area, and description equal the submitted values, whose status is `Pending`, and whose Complaint_ID in the lookup response equals the Complaint_ID returned at submission.

**Validates: Requirements 1.3, 1.7, 2.2, 5.1, 5.2, 5.3**

### Property 2: Complaint IDs are well-formed and unique

*For any* sequence of valid complaint submissions, every returned Complaint_ID matches the pattern `NGP-<four-digit-year>-<sequence>`, and no two submitted complaints share the same Complaint_ID.

**Validates: Requirements 1.4, 5.4**

### Property 3: Creation invariants — pending status and valid timestamps

*For any* valid complaint submission, the created record has status `Pending`, a creation timestamp, and a last-updated timestamp, with the creation timestamp not later than the last-updated timestamp.

**Validates: Requirements 1.5, 1.6**

### Property 4: Photo reference conditional persistence

*For any* valid complaint submission, the persisted record has a non-empty photo reference if and only if a photo file was attached to that submission.

**Validates: Requirements 1.11**

### Property 5: Incomplete submissions are rejected without persistence

*For any* submission missing at least one required field (citizen name, category, location area, or description), the Backend_API returns a validation error and the total number of persisted complaint records is unchanged.

**Validates: Requirements 1.9**

### Property 6: Unknown Complaint_ID returns not-found

*For any* Complaint_ID that does not correspond to a persisted complaint, a tracking lookup for that ID returns a not-found response.

**Validates: Requirements 2.4**

### Property 7: Lookup consistency (read idempotence)

*For any* persisted complaint, repeated tracking lookups by its Complaint_ID return identical complaint data every time, independent of how many times or from which client the lookup is performed.

**Validates: Requirements 5.5**

### Property 8: Undefined routes return not-found

*For any* request path that matches neither a static asset nor a defined API route, the Backend_API returns a not-found error response.

**Validates: Requirements 5.6**

### Property 9: Navigation and stylesheet completeness across all pages

*For any* of the five pages (Home, Report, Track, Dashboard, About), the page contains navigation links to each of the other four pages and references the shared stylesheet.

**Validates: Requirements 4.3, 4.4**

### Property 10: Header tags are well-formed across all pages

*For any* of the five pages, every opening header tag has a corresponding correctly placed closing tag (the page parses with no unclosed or malformed header elements).

**Validates: Requirements 6.1**

### Property 11: All HTML class references resolve in the stylesheet

*For any* CSS class referenced by any of the five HTML pages, a matching selector is defined in the shared stylesheet.

**Validates: Requirements 6.4**
