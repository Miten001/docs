# Requirements Document

## Introduction

NagrikSetu is a civic engagement platform that enables citizens of Nagpur to report local civic problems, track the status of their submitted complaints, view a civic dashboard, and learn about the project's mission. This feature converts a set of static HTML pages into a functional website backed by a Node.js + Express server and a SQLite database, so that complaints are persisted and shared across all users and devices.

The system consists of a browser-based frontend (five HTML pages, shared styling, and an ES module script) and a backend REST API. When a citizen submits a complaint, the backend generates and returns a unique, human-readable Complaint ID (for example, `NGP-2024-0042`). The citizen uses this Complaint ID on the Track page to retrieve the current status and details of the complaint. The Civic Dashboard displays static demonstration values in this release. Existing HTML defects (malformed tags, spelling errors, and inconsistent class names) are corrected as part of this work.

## Glossary

- **NagrikSetu**: The civic platform described by this document, comprising the Frontend and the Backend_API.
- **System**: The complete NagrikSetu solution, including the Frontend and the Backend_API.
- **Frontend**: The browser-delivered pages, shared stylesheet, and client-side ES module that render the interface and communicate with the Backend_API.
- **Backend_API**: The Node.js and Express server that exposes REST endpoints and reads from and writes to the Database.
- **Database**: The SQLite datastore that persists Complaint records.
- **Complaint**: A citizen-reported civic problem record containing category, description, location area, citizen name, optional contact, optional photo, status, Complaint_ID, and timestamps.
- **Complaint_ID**: A unique, auto-generated, human-readable identifier assigned to each Complaint at submission time, formatted as `NGP-<year>-<sequence>` (for example, `NGP-2024-0042`).
- **Category**: The classification of a Complaint, one of Pothole, Garbage, Water, Traffic, or Other.
- **Status**: The lifecycle state of a Complaint, one of Pending, In Progress, or Resolved.
- **Citizen**: A person using NagrikSetu to report or track a civic problem.
- **Report_Page**: The `report.html` page containing the complaint submission form.
- **Track_Page**: The `track.html` page used to look up a Complaint by Complaint_ID.
- **Dashboard_Page**: The `dashboard.html` page displaying static demonstration civic statistics.
- **Home_Page**: The `index.html` landing page.
- **About_Page**: The `about.html` page describing the mission of NagrikSetu.

## Requirements

### Requirement 1: Complaint Submission

**User Story:** As a citizen, I want to submit a civic problem report through a form, so that the relevant authorities have a persistent record of the issue.

#### Acceptance Criteria

1. THE Report_Page SHALL present a form with fields for citizen name, problem category, location area, description, optional contact, and optional photo upload.
2. THE Report_Page SHALL offer the Category field as a selection limited to Pothole, Garbage, Water, Traffic, and Other.
3. WHEN a Citizen submits the form with citizen name, Category, location area, and description all populated, THE Backend_API SHALL create a Complaint record in the Database.
4. WHEN the Backend_API creates a Complaint record, THE Backend_API SHALL assign a unique Complaint_ID formatted as `NGP-<year>-<sequence>`.
5. WHEN the Backend_API creates a Complaint record, THE Backend_API SHALL set the Status to Pending.
6. WHEN the Backend_API creates a Complaint record, THE Backend_API SHALL store a creation timestamp and a last-updated timestamp.
7. WHEN the Backend_API successfully creates a Complaint record, THE Backend_API SHALL return a response containing the assigned Complaint_ID.
8. WHEN the Backend_API returns a successful submission response, THE Report_Page SHALL display the assigned Complaint_ID to the Citizen.
9. IF a Citizen submits the form while citizen name, Category, location area, or description is missing, THEN THE Backend_API SHALL reject the request with a validation error response and SHALL NOT create a Complaint record.
10. IF a Citizen submits the form while a required field is missing, THEN THE Report_Page SHALL display a validation message identifying the missing input.
11. WHERE a photo file is attached, THE Backend_API SHALL store a reference to the uploaded photo with the Complaint record.

### Requirement 2: Complaint Tracking

**User Story:** As a citizen, I want to look up my complaint using its Complaint ID, so that I can see the current status and details.

#### Acceptance Criteria

1. THE Track_Page SHALL present an input field for a Complaint_ID and a control to submit the lookup.
2. WHEN a Citizen submits a Complaint_ID that matches an existing Complaint record, THE Backend_API SHALL return the matching Complaint's Category, location area, description, Status, and creation timestamp.
3. WHEN the Backend_API returns a matching Complaint, THE Track_Page SHALL display the Complaint's Status, Category, location area, description, and creation timestamp.
4. IF a Citizen submits a Complaint_ID that matches no Complaint record, THEN THE Backend_API SHALL return a not-found response.
5. IF the Backend_API returns a not-found response, THEN THE Track_Page SHALL display a message stating that no Complaint matches the entered Complaint_ID.
6. IF a Citizen submits the lookup while the Complaint_ID input is empty, THEN THE Track_Page SHALL display a message prompting the Citizen to enter a Complaint_ID and SHALL NOT send a lookup request.

### Requirement 3: Civic Dashboard

**User Story:** As a citizen, I want to view a civic dashboard, so that I can see an overview of reported problems at a glance.

#### Acceptance Criteria

1. THE Dashboard_Page SHALL display static demonstration complaint counts grouped by Category for Pothole, Garbage, Water, Traffic, and Other.
2. THE Dashboard_Page SHALL display static demonstration complaint counts grouped by Status for Pending, In Progress, and Resolved.

### Requirement 4: Informational Pages and Navigation

**User Story:** As a citizen, I want a home page, an about page, and consistent navigation, so that I can understand the platform and move between its sections.

#### Acceptance Criteria

1. THE Home_Page SHALL present an introduction to NagrikSetu and navigation links to the Report_Page, the Track_Page, the Dashboard_Page, and the About_Page.
2. THE About_Page SHALL present the mission of NagrikSetu and a description of how NagrikSetu helps Citizens.
3. THE Home_Page, Report_Page, Track_Page, Dashboard_Page, and About_Page SHALL each present navigation links to the other four pages.
4. THE Home_Page, Report_Page, Track_Page, Dashboard_Page, and About_Page SHALL apply the shared stylesheet for consistent visual presentation.

### Requirement 5: Backend Service and Data Persistence

**User Story:** As a platform operator, I want complaints persisted in a shared database through a REST API, so that all citizens see consistent complaint data across devices.

#### Acceptance Criteria

1. THE Backend_API SHALL expose an endpoint that accepts a complaint submission and returns the generated Complaint_ID.
2. THE Backend_API SHALL expose an endpoint that accepts a Complaint_ID and returns the corresponding Complaint's status and details.
3. THE Backend_API SHALL persist each Complaint record in the Database with fields for Category, description, location area, citizen name, optional contact, optional photo reference, Status, Complaint_ID, creation timestamp, and last-updated timestamp.
4. THE Backend_API SHALL assign each Complaint_ID such that no two Complaint records share the same Complaint_ID.
5. WHILE the Database contains persisted Complaint records, THE Backend_API SHALL return the same Complaint data for a given Complaint_ID regardless of which Citizen or device requests it.
6. IF the Backend_API receives a request to an undefined route, THEN THE Backend_API SHALL return a not-found error response.

### Requirement 6: HTML Defect Correction

**User Story:** As a maintainer, I want the existing HTML defects corrected, so that the pages render correctly and use consistent naming.

#### Acceptance Criteria

1. THE Frontend SHALL provide HTML in which every opening header tag has a corresponding correctly placed closing tag.
2. THE Frontend SHALL correct spelling errors in page text, including the misspelling "placeholdeer".
3. THE Frontend SHALL use consistent CSS class names, replacing inconsistent identifiers such as "staus-section" and "satus progress" with correctly spelled equivalents.
4. THE Frontend SHALL reference CSS class names in the shared stylesheet that match the class names used in the HTML pages.
