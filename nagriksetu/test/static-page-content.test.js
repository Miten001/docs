// Task 9.6 — Unit tests for static page content.
// Validates Requirements 1.1, 1.2, 3.1, 3.2, 4.1, 4.2, 6.2.
//
// These are example/unit-based assertions (behavior does not vary with input):
// they read the delivered HTML pages from disk and assert on their content.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = join(__dirname, '..', 'public');

const PAGES = ['index.html', 'report.html', 'track.html', 'dashboard.html', 'about.html'];

function read(page) {
  return readFileSync(join(PUBLIC_DIR, page), 'utf8');
}

const CATEGORIES = ['Pothole', 'Garbage', 'Water', 'Traffic', 'Other'];

test('report.html presents all required form fields (Req 1.1)', () => {
  const html = read('report.html');
  // Citizen name, location area, description, optional contact, optional photo.
  assert.match(html, /name="name"/, 'expected a citizen name field');
  assert.match(html, /name="locationArea"/, 'expected a location/area field');
  assert.match(html, /name="description"/, 'expected a description field');
  assert.match(html, /name="contact"/, 'expected an optional contact field');
  assert.match(html, /name="photo"/, 'expected an optional photo upload field');
  // Photo field is a file input.
  assert.match(html, /type="file"[^>]*name="photo"|name="photo"[^>]*type="file"/,
    'expected the photo field to be a file input');
});

test('report.html offers the Category field as a select limited to the five categories (Req 1.2)', () => {
  const html = read('report.html');
  // There is a <select> for the category.
  assert.match(html, /<select[^>]*name="category"[^>]*>[\s\S]*?<\/select>/,
    'expected a <select> element for category');
  const select = html.match(/<select[^>]*name="category"[^>]*>([\s\S]*?)<\/select>/)[1];
  // Each of the five categories is offered as an option.
  for (const category of CATEGORIES) {
    assert.match(select, new RegExp(`<option[^>]*value="${category}"[^>]*>`),
      `expected an option for category "${category}"`);
  }
  // No categories outside the allowed set are offered as selectable values.
  const optionValues = [...select.matchAll(/<option[^>]*value="([^"]*)"/g)]
    .map((m) => m[1])
    .filter((v) => v.length > 0); // ignore the empty placeholder option
  for (const value of optionValues) {
    assert.ok(CATEGORIES.includes(value), `unexpected category option value: "${value}"`);
  }
  assert.equal(new Set(optionValues).size, CATEGORIES.length,
    'expected exactly the five allowed category options');
});

test('dashboard.html shows demonstration complaint counts grouped by category (Req 3.1)', () => {
  const html = read('dashboard.html');
  const expectedCounts = {
    Pothole: '24',
    Garbage: '18',
    Water: '12',
    Traffic: '15',
    Other: '7',
  };
  for (const [label, count] of Object.entries(expectedCounts)) {
    assert.match(html, new RegExp(`>\\s*${label}\\s*<`),
      `expected a category label for "${label}"`);
    assert.match(html, new RegExp(`>\\s*${count}\\s*<`),
      `expected the demo count "${count}" for category "${label}"`);
  }
});

test('dashboard.html shows demonstration complaint counts grouped by status (Req 3.2)', () => {
  const html = read('dashboard.html');
  const expectedStatus = {
    Resolved: '42',
    'In Progress': '25',
    Pending: '18',
  };
  for (const [label, count] of Object.entries(expectedStatus)) {
    assert.match(html, new RegExp(`>\\s*${label}\\s*<`),
      `expected a status label for "${label}"`);
    assert.match(html, new RegExp(`>\\s*${count}\\s*<`),
      `expected the demo count "${count}" for status "${label}"`);
  }
});

test('index.html introduces NagrikSetu (Req 4.1)', () => {
  const html = read('index.html');
  assert.match(html, /NagrikSetu/, 'expected the home page to mention NagrikSetu');
  assert.match(html, /civic engagement platform/i,
    'expected the home page to introduce NagrikSetu as a civic engagement platform');
});

test('about.html presents the mission of NagrikSetu (Req 4.2)', () => {
  const html = read('about.html');
  assert.match(html, /mission/i, 'expected the about page to describe the mission');
  assert.match(html, /How NagrikSetu Helps Citizens/i,
    'expected the about page to describe how NagrikSetu helps citizens');
});

test('no page contains the "placeholdeer" misspelling (Req 6.2)', () => {
  for (const page of PAGES) {
    const html = read(page);
    assert.ok(!/placeholdeer/i.test(html),
      `${page} must not contain the "placeholdeer" misspelling`);
  }
});

test('no page contains the defective class names "staus-section" or "satus progress" (Req 6.2/6.3)', () => {
  for (const page of PAGES) {
    const html = read(page);
    assert.ok(!/staus-section/.test(html),
      `${page} must not contain the defective class name "staus-section"`);
    assert.ok(!/satus progress/.test(html),
      `${page} must not contain the defective class name "satus progress"`);
  }
});
