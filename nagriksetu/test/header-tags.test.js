// Task 11.2 — Property 10: Header tags are well-formed across all pages.
// Validates Requirements 6.1.
//
// Feature: nagriksetu-website, Property 10: For any of the five pages, every
// opening header tag has a corresponding correctly placed closing tag: the
// count of <header> equals the count of </header> (balanced) and there are no
// stray/misplaced closing header tags (no </header> appears before its <header>).

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

// Collect header open/close tags in document order and walk them, tracking
// nesting depth. A well-formed page never lets depth go negative (which would
// mean a stray/misplaced </header>) and ends at depth 0 (balanced).
function analyzeHeaderTags(html) {
  const tagRe = /<(\/?)header\b[^>]*>/gi;
  let depth = 0;
  let minDepth = 0;
  let opens = 0;
  let closes = 0;
  let match;
  while ((match = tagRe.exec(html)) !== null) {
    const isClosing = match[1] === '/';
    if (isClosing) {
      closes += 1;
      depth -= 1;
    } else {
      opens += 1;
      depth += 1;
    }
    if (depth < minDepth) minDepth = depth;
  }
  return { opens, closes, finalDepth: depth, minDepth };
}

test('Feature: nagriksetu-website, Property 10: Header tags are well-formed across all pages', () => {
  fc.assert(
    fc.property(fc.constantFrom(...PAGES), (page) => {
      const html = read(page);
      const { opens, closes, finalDepth, minDepth } = analyzeHeaderTags(html);

      // Balanced: equal number of opening and closing header tags.
      assert.equal(opens, closes,
        `${page} has ${opens} <header> tag(s) but ${closes} </header> tag(s)`);

      // No stray/misplaced closing tag: depth never drops below zero, so no
      // </header> ever appears before a matching <header>.
      assert.ok(minDepth >= 0,
        `${page} contains a </header> that appears before its matching <header>`);

      // Fully closed by the end of the document.
      assert.equal(finalDepth, 0,
        `${page} has an unclosed <header> element`);
    }),
    { numRuns: 100 },
  );
});
