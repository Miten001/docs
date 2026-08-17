// Task 11.1 — Property 9: Navigation and stylesheet completeness across all pages.
// Validates Requirements 4.3, 4.4.
//
// Feature: nagriksetu-website, Property 9: For any of the five pages (Home,
// Report, Track, Dashboard, About), the page contains navigation links to each
// of the other four pages and references the shared stylesheet.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import fc from 'fast-check';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = join(__dirname, '..', 'public');

const PAGES = ['index.html', 'report.html', 'track.html', 'dashboard.html', 'about.html'];

function read(page) {
  return readFileSync(join(PUBLIC_DIR, page), 'utf8');
}

test('Feature: nagriksetu-website, Property 9: Navigation and stylesheet completeness across all pages', () => {
  fc.assert(
    fc.property(fc.constantFrom(...PAGES), (page) => {
      const html = read(page);

      // Req 4.4 — the page references the shared stylesheet.
      assert.match(html, /<link[^>]*rel="stylesheet"[^>]*href="style\.css"|<link[^>]*href="style\.css"[^>]*rel="stylesheet"/,
        `${page} must link the shared stylesheet style.css`);

      // Req 4.3 — the page contains navigation links to each of the other four pages.
      const others = PAGES.filter((p) => p !== page);
      for (const other of others) {
        assert.match(html, new RegExp(`href="${other.replace('.', '\\.')}"`),
          `${page} must contain a navigation link to ${other}`);
      }
    }),
    { numRuns: 100 },
  );
});
