// Task 11.3 — Property 11: All HTML class references resolve in the stylesheet.
// Validates Requirements 6.4.
//
// Feature: nagriksetu-website, Property 11: For any CSS class referenced by any
// of the five HTML pages, a matching selector (.classname) is defined in the
// shared stylesheet.

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

const STYLESHEET = readFileSync(join(PUBLIC_DIR, 'style.css'), 'utf8');

// Extract the distinct set of class names referenced in class="..." attributes.
function classesInPage(html) {
  const classes = new Set();
  for (const match of html.matchAll(/class="([^"]*)"/g)) {
    for (const name of match[1].split(/\s+/)) {
      if (name.length > 0) classes.add(name);
    }
  }
  return [...classes];
}

// A stylesheet defines a class when it contains a `.classname` selector token
// not followed by another identifier character (so `.status` does not spuriously
// match `.status-progress`).
function stylesheetDefinesClass(className) {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const selectorRe = new RegExp(`\\.${escaped}(?![\\w-])`);
  return selectorRe.test(STYLESHEET);
}

test('Feature: nagriksetu-website, Property 11: All HTML class references resolve in the stylesheet', () => {
  fc.assert(
    fc.property(fc.constantFrom(...PAGES), (page) => {
      const html = read(page);
      const classes = classesInPage(html);
      for (const className of classes) {
        assert.ok(stylesheetDefinesClass(className),
          `${page} references class "${className}" but no matching selector ".${className}" exists in style.css`);
      }
    }),
    { numRuns: 100 },
  );
});
