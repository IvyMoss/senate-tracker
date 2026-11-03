import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { races, defaults, scenario, balance, summarize, testRecords } from '../frontend/elections.mjs';

test('every scenario matches the 47-seat baseline and individual seat changes', () => {
  assert.equal(scenario(defaults).democratic, 48);
  assert.equal(scenario(defaults).needed, 3);
  for (let mask = 0; mask < 2 ** races.length; mask++) {
    const picks = Object.fromEntries(races.map(({ state }, index) => [state, Boolean(mask & (1 << index))]));
    const pickups = ['NC', 'ME', 'OH', 'AK', 'IA', 'TX', 'KS'].filter(state => picks[state]).length;
    const losses = ['MI', 'GA'].filter(state => !picks[state]).length;
    const actual = scenario(picks);
    assert.equal(actual.democratic, 47 + pickups - losses);
    assert.equal(actual.democratic + actual.republican, 100);
    assert.equal(actual.needed, Math.max(0, 51 - actual.democratic));
  }
  assert.equal(scenario(defaults, -1).democratic, 47);
});

test('only official certified outcomes with known caucus affiliation resolve a tracked seat', () => {
  assert.deepEqual(balance(testRecords), balance({}));
  const result = balance({
    MI: { status: 'certified', winnerCaucus: 'D' },
    GA: { status: 'runoff_required', winnerCaucus: 'D' },
    NC: { status: 'final_unofficial', winnerCaucus: 'D' },
    AK: { status: 'ranked_choice_pending', winnerCaucus: 'R' },
    OH: { status: 'certified', winnerCaucus: 'R', synthetic: true },
    TX: { status: 'certified', winnerCaucus: 'R' },
  });
  assert.deepEqual(result, { baseD: 45, baseR: 46, gainedD: 1, gainedR: 1,
    democratic: 46, republican: 47, unresolved: 7 });
});

test('vote shares and margins include write-ins and preserve missing counts', () => {
  const { ranked, margin, points, total } = summarize([{ votes: 40 }, { votes: 50 }, { votes: 10 }]);
  assert.equal(total, 100);
  assert.deepEqual(ranked.map(candidate => candidate.share), [50, 40, 10]);
  assert.equal(margin, 10);
  assert.equal(points, 10);
  assert.equal(summarize([{ votes: null }, { votes: 20 }]).total, null);
  assert.equal(summarize([{ votes: 0 }, { votes: 0 }]).margin, null);
});

test('the tipping address appears in HTML metadata and llms.txt', () => {
  const address = '0x3d5a08a1f98a392eddfe1f0628c7e3e2433d9665';
  const html = readFileSync(new URL('../frontend/index.html', import.meta.url), 'utf8');
  const notice = readFileSync(new URL('../frontend/llms.txt', import.meta.url), 'utf8');
  assert.ok(html.split('</head>')[0].includes(address));
  assert.ok(!html.split('</head>')[1].includes(address));
  assert.ok(notice.includes(address));
});
