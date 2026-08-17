// Task 10.2 — Unit tests for client DOM rendering.
// Validates Requirements 1.8, 1.10, 2.3, 2.5, 2.6.
//
// These are example/unit-based tests. They exercise the client ES module
// (public/script.js) against a simulated DOM built with jsdom and a stubbed
// global fetch(). The exported handlers (handleReportSubmit, handleTrackSubmit)
// read form values via document.getElementById and render results into the
// message / status elements, so we assign global.document / global.window from
// a JSDOM instance and restore the globals after each test.

import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

import {
  handleReportSubmit,
  handleTrackSubmit,
  statusVariantClass,
} from '../public/script.js';

// Preserve the real globals so tests never leak DOM / fetch state to others.
const ORIGINAL_FETCH = global.fetch;
const ORIGINAL_DOCUMENT = global.document;
const ORIGINAL_WINDOW = global.window;

afterEach(() => {
  global.fetch = ORIGINAL_FETCH;
  if (ORIGINAL_DOCUMENT === undefined) delete global.document;
  else global.document = ORIGINAL_DOCUMENT;
  if (ORIGINAL_WINDOW === undefined) delete global.window;
  else global.window = ORIGINAL_WINDOW;
});

// ---------------------------------------------------------------------------
// DOM fixtures mirroring the relevant report.html / track.html elements.
// ---------------------------------------------------------------------------

const REPORT_BODY = `
  <form id="reportForm">
    <input id="name" name="name" />
    <select id="category" name="category">
      <option value=""></option>
      <option value="Pothole">Pothole</option>
      <option value="Garbage">Garbage</option>
      <option value="Water">Water</option>
      <option value="Traffic">Traffic</option>
      <option value="Other">Other</option>
    </select>
    <input id="locationArea" name="locationArea" />
    <textarea id="description" name="description"></textarea>
    <input id="contact" name="contact" />
    <input id="photo" name="photo" type="file" />
    <button id="submitComplaint" type="submit">Submit</button>
  </form>
  <div id="reportMessage"></div>
`;

const TRACK_BODY = `
  <form id="trackForm">
    <input id="complaintId" name="complaintId" />
    <button id="trackButton" type="submit">Track</button>
  </form>
  <div id="statusBox">
    <div id="statusText"></div>
  </div>
`;

function setupDom(bodyHtml) {
  const dom = new JSDOM(`<!DOCTYPE html><html><body>${bodyHtml}</body></html>`);
  global.window = dom.window;
  global.document = dom.window.document;
  return dom;
}

/**
 * Install a fetch stub that records every call and returns a Response-like
 * object built from { status, body }. Returns the calls array for assertions.
 */
function stubFetch(response) {
  const calls = [];
  global.fetch = async (...args) => {
    calls.push(args);
    return {
      status: response.status,
      json: async () => response.body ?? {},
    };
  };
  return calls;
}

/**
 * Install a fetch stub that fails the test if it is ever invoked. Used to
 * assert the "no request is sent" behaviors (Req 1.10, 2.6).
 */
function forbidFetch() {
  const calls = [];
  global.fetch = async (...args) => {
    calls.push(args);
    throw new Error('fetch must not be called');
  };
  return calls;
}

function fill(id, value) {
  global.document.getElementById(id).value = value;
}

// ---------------------------------------------------------------------------
// Report page (Req 1.8, 1.10)
// ---------------------------------------------------------------------------

test('Req 1.8: report success renders the returned Complaint ID', async () => {
  const dom = setupDom(REPORT_BODY);
  const form = dom.window.document.getElementById('reportForm');
  const messageBox = dom.window.document.getElementById('reportMessage');

  fill('name', 'Asha Kumar');
  fill('category', 'Pothole');
  fill('locationArea', 'Dharampeth');
  fill('description', 'Large pothole near the market');

  const calls = stubFetch({
    status: 201,
    body: { complaintId: 'NGP-2024-0042', status: 'Pending' },
  });

  await handleReportSubmit(form, messageBox);

  // The request was sent (a valid form must reach the backend).
  assert.equal(calls.length, 1, 'expected exactly one fetch call');
  assert.equal(calls[0][0], '/api/complaints');

  // The returned Complaint ID is displayed to the citizen (Req 1.8).
  assert.match(
    messageBox.innerHTML,
    /NGP-2024-0042/,
    'expected the returned Complaint ID to be shown',
  );
  assert.match(messageBox.className, /success/, 'expected a success message');
});

test('Req 1.10: missing required field shows a validation message and sends no request', async () => {
  const dom = setupDom(REPORT_BODY);
  const form = dom.window.document.getElementById('reportForm');
  const messageBox = dom.window.document.getElementById('reportMessage');

  // Everything filled except the description (a required field).
  fill('name', 'Asha Kumar');
  fill('category', 'Pothole');
  fill('locationArea', 'Dharampeth');
  fill('description', '   '); // whitespace-only counts as missing

  const calls = forbidFetch();

  await handleReportSubmit(form, messageBox);

  // No request is sent for a known-empty required field (Req 1.10).
  assert.equal(calls.length, 0, 'expected fetch not to be called');

  // The message names/lists the missing input by its human-readable label.
  assert.match(messageBox.className, /error/, 'expected an error message');
  assert.match(
    messageBox.innerHTML,
    /Describe the Problem/,
    'expected the missing "description" field to be named',
  );
});

// ---------------------------------------------------------------------------
// Track page (Req 2.3, 2.5, 2.6)
// ---------------------------------------------------------------------------

test('Req 2.3: track details render status, category, area, description with the correct badge variant', async () => {
  const dom = setupDom(TRACK_BODY);
  const statusText = dom.window.document.getElementById('statusText');

  fill('complaintId', 'NGP-2024-0042');

  const complaint = {
    complaintId: 'NGP-2024-0042',
    category: 'Pothole',
    locationArea: 'Dharampeth',
    description: 'Large pothole near the market',
    status: 'In Progress',
    createdAt: '2024-05-01T09:30:00.000Z',
  };
  const calls = stubFetch({ status: 200, body: complaint });

  await handleTrackSubmit(statusText);

  assert.equal(calls.length, 1, 'expected exactly one fetch call');
  assert.match(calls[0][0], /\/api\/complaints\/NGP-2024-0042/);

  const html = statusText.innerHTML;
  assert.match(html, /In Progress/, 'expected the status to be rendered');
  assert.match(html, /Pothole/, 'expected the category to be rendered');
  assert.match(html, /Dharampeth/, 'expected the location area to be rendered');
  assert.match(
    html,
    /Large pothole near the market/,
    'expected the description to be rendered',
  );

  // The correct status-badge variant class is applied (In Progress -> status-progress).
  assert.equal(statusVariantClass('In Progress'), 'status-progress');
  assert.match(html, /status-badge/, 'expected a status badge element');
  assert.match(
    html,
    /status-progress/,
    'expected the In-Progress badge variant class',
  );
});

test('Req 2.5: track not-found shows a "no complaint matches" message', async () => {
  const dom = setupDom(TRACK_BODY);
  const statusText = dom.window.document.getElementById('statusText');

  fill('complaintId', 'NGP-2024-9999');

  stubFetch({
    status: 404,
    body: {
      error: 'NotFound',
      message: 'No complaint matches the entered Complaint ID.',
    },
  });

  await handleTrackSubmit(statusText);

  assert.match(
    statusText.innerHTML,
    /no complaint matches/i,
    'expected a not-found message',
  );
});

test('Req 2.6: empty Complaint ID shows a prompt and sends no request', async () => {
  const dom = setupDom(TRACK_BODY);
  const statusText = dom.window.document.getElementById('statusText');

  fill('complaintId', '   '); // whitespace-only

  const calls = forbidFetch();

  await handleTrackSubmit(statusText);

  assert.equal(calls.length, 0, 'expected fetch not to be called');
  assert.match(
    statusText.innerHTML,
    /enter a Complaint ID/i,
    'expected a prompt to enter a Complaint ID',
  );
});
