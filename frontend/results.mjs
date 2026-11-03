import { races } from './elections.mjs';

const interval = 30_000;
const validStates = new Set(races.map(({ state }) => state));
const feedOnlyStates = new Set(['FL', 'SC']);
const validStatuses = new Set([
  'reporting', 'leading', 'unresolved', 'runoff_required',
  'ranked_choice_pending', 'final_unofficial', 'certified',
]);
const isCount = value => Number.isSafeInteger(value) && value >= 0;

export function validateSnapshot(snapshot) {
  if (snapshot?.electionDate !== '2026-11-03' || !snapshot.records ||
      typeof snapshot.records !== 'object' || Array.isArray(snapshot.records)) {
    throw new Error('Invalid election snapshot');
  }
  for (const [state, record] of Object.entries(snapshot.records)) {
    if ((!validStates.has(state) && !feedOnlyStates.has(state)) || !validStatuses.has(record?.status) ||
        record.synthetic || !Array.isArray(record.candidates) ||
        record.candidates.some(candidate => !candidate ||
          typeof candidate.name !== 'string' || !candidate.name.trim() ||
          typeof candidate.party !== 'string' || !candidate.party.trim() ||
          (candidate.votes !== null && !isCount(candidate.votes))) ||
        (record.sourceUpdatedAt != null && (typeof record.sourceUpdatedAt !== 'string' ||
          !Number.isFinite(Date.parse(record.sourceUpdatedAt)))) ||
        (record.reportingPercent != null && (!Number.isFinite(record.reportingPercent) ||
          record.reportingPercent < 0 || record.reportingPercent > 100)) ||
        (record.reporting != null || record.reportingTotal != null) &&
          (!isCount(record.reporting) || !isCount(record.reportingTotal) ||
            record.reportingTotal === 0 || record.reporting > record.reportingTotal ||
            typeof record.reportingUnit !== 'string')) {
      throw new Error('Invalid result record for ' + state);
    }
  }
  return snapshot.records;
}

export async function pollResults(onResults, onError) {
  try {
    const response = await fetch(new URL('./results.json', import.meta.url), {
      cache: 'no-cache',
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) throw new Error('Results request failed');
    const records = validateSnapshot(await response.json());
    onResults(Object.fromEntries(Object.entries(records).filter(([state]) => validStates.has(state))));
  } catch {
    onError();
  } finally {
    setTimeout(() => pollResults(onResults, onError), interval);
  }
}
