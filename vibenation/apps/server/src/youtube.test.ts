// Guards the "no stutter" rule: every YouTube broadcast uses normal latency.
// Run: pnpm --filter @vibenation/server test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { LATENCY, withNormalLatency } from './youtube.js';

test('broadcasts use normal latency', () => {
  assert.equal(LATENCY, 'normal');
  const cd = withNormalLatency({ enableAutoStart: true, latencyPreference: 'ultraLow', enableLowLatency: true });
  assert.equal(cd.latencyPreference, 'normal');
  assert.equal(cd.enableLowLatency, false);
});

test('no code sets low or ultra-low latency', () => {
  for (const f of ['youtube.ts', 'golive.ts']) {
    const src = readFileSync(new URL(`./${f}`, import.meta.url), 'utf8');
    assert.doesNotMatch(src, /latencyPreference:\s*['"](low|ultraLow)['"]/, f);
    assert.doesNotMatch(src, /enableLowLatency:\s*true/, f);
  }
});
