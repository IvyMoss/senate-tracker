import { randomUUID } from 'node:crypto';
import { readFile, rename, rm, writeFile } from 'node:fs/promises';
import { validateSnapshot } from '../frontend/results.mjs';
import { collectNorthCarolina } from './north-carolina.mjs';

if (process.argv.includes('--print-nc')) {
  const record = await collectNorthCarolina();
  validateSnapshot({ electionDate: '2026-11-03', records: { NC: record } });
  const votes = record.candidates.reduce((total, candidate) => total + (candidate.votes ?? 0), 0);
  console.error(record.status === 'reporting'
    ? `North Carolina archive contains ${votes.toLocaleString('en-US')} Senate votes.`
    : `North Carolina archive contains ${record.candidates.length} Senate candidates and no reported votes.`);
  await new Promise((resolve, reject) => {
    process.stdout.write(JSON.stringify(record) + '\n', error => error ? reject(error) : resolve());
  });
  process.exit(0);
}

const output = new URL('../frontend/results.json', import.meta.url);
const snapshot = JSON.parse(await readFile(output, 'utf8'));
validateSnapshot(snapshot);
const record = await collectNorthCarolina();
if (snapshot.records.NC?.status === 'certified') {
  console.log('Preserved the existing certified North Carolina result.');
} else if (record.candidates.every(candidate => candidate.votes === null) &&
           snapshot.records.NC?.candidates.some(candidate => candidate.votes !== null)) {
  throw new Error('North Carolina archive returned to a pre-reporting state. Preserved the last snapshot.');
} else {
  const updated = { ...snapshot, records: { ...snapshot.records, NC: record } };
  validateSnapshot(updated);
  if (JSON.stringify(updated) !== JSON.stringify(snapshot)) {
    const temporary = new URL(`results.${randomUUID()}.tmp`, output);
    try {
      await writeFile(temporary, JSON.stringify(updated, null, 2) + '\n', { flag: 'wx' });
      await rename(temporary, output);
    } finally {
      await rm(temporary, { force: true });
    }
  }
  console.log('North Carolina snapshot checked.');
}
