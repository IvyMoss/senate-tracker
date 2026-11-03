export const races = [
  ['MI', 'Michigan', 'Michigan Secretary of State', 'https://mvic.sos.state.mi.us/votehistory/Index?electionDate=11-3-2026&type=C', 'D'],
  ['GA', 'Georgia', 'Georgia Secretary of State', 'https://results.sos.ga.gov/results/public/Georgia/11032026GeneralAndSpecialElection', 'D'],
  ['NC', 'North Carolina', 'North Carolina State Board of Elections', 'https://er.ncsbe.gov/', 'R'],
  ['ME', 'Maine', 'Maine Secretary of State', 'https://www.maine.gov/sos/elections-voting/election-results-data', 'R'],
  ['OH', 'Ohio', 'Ohio Secretary of State', 'https://liveresults.ohiosos.gov/', 'R'],
  ['AK', 'Alaska', 'Alaska Division of Elections', 'https://www.elections.alaska.gov/election-results/', 'R'],
  ['IA', 'Iowa', 'Iowa Secretary of State', 'https://electionresults.iowa.gov/IA/127077/web.345435/#/detail/1000', 'R'],
  ['TX', 'Texas', 'Texas Secretary of State', 'https://electionresults.sos.state.tx.us/results.html', 'R'],
  ['KS', 'Kansas', 'Kansas Secretary of State', 'https://www.sos.ks.gov/elections/election-results.html', 'R'],
].map(([state, name, authority, url, incumbent]) => ({ state, name, authority, url, incumbent }));

export const dreamingRaces = [
  { state: 'FL', name: 'Florida', authority: 'Florida Division of Elections',
    url: 'https://floridaelectionwatch.gov/', election: 'Special election' },
  { state: 'SC', name: 'South Carolina', authority: 'South Carolina Election Commission',
    url: 'https://scvotes.gov/elections-statistics/election-results/' },
];

export const defaults = Object.fromEntries(races.map(({ state }) => [state, ['MI', 'GA', 'NC'].includes(state)]));
export const additional = races.slice(3);

export function scenario(assumptions, outsideNet = 0) {
  const democratic = 45 + races.filter(({ state }) => assumptions[state]).length + outsideNet;
  const flipsRemaining = additional.filter(({ state }) => !assumptions[state]).length;
  const needed = Math.max(0, 51 - democratic);
  return { democratic, republican: 100 - democratic, net: democratic - 47, needed, flipsRemaining };
}

export function resolvedParty(record) {
  if (record?.synthetic || record?.status !== 'certified') return null;
  return ['D', 'R'].includes(record.winnerCaucus) ? record.winnerCaucus : null;
}

export function balance(records, outsideNet = 0) {
  const baseD = 47 - races.filter(race => race.incumbent === 'D').length + outsideNet;
  const baseR = 100 - races.length - baseD;
  const parties = races.map(({ state }) => resolvedParty(records[state]));
  const gainedD = parties.filter(party => party === 'D').length;
  const gainedR = parties.filter(party => party === 'R').length;
  return { baseD, baseR, gainedD, gainedR, democratic: baseD + gainedD,
    republican: baseR + gainedR, unresolved: parties.filter(party => party === null).length };
}

export function summarize(candidates) {
  if (!candidates.length || candidates.some(({ votes }) => !Number.isSafeInteger(votes) || votes < 0)) {
    return { total: null, ranked: candidates, margin: null, points: null };
  }
  const total = candidates.reduce((sum, candidate) => sum + candidate.votes, 0);
  const ranked = candidates.toSorted((a, b) => b.votes - a.votes).map(candidate => ({
    ...candidate, share: total > 0 ? 100 * candidate.votes / total : null,
  }));
  const margin = total > 0 && ranked.length >= 2 ? ranked[0].votes - ranked[1].votes : null;
  return { total, ranked, margin, points: margin === null ? null : 100 * margin / total };
}

// Synthetic fixture. The public view starts with no result records.
export const testRecords = Object.fromEntries(races.slice(0, 6).map(({ state }, index) => [state, {
  status: index === 5 ? 'ranked_choice_pending' : 'reporting',
  synthetic: true,
  sourceUpdatedAt: new Date(Date.UTC(2026, 10, 4, 2, index)).toISOString(),
  reporting: 20 + index * 12,
  reportingTotal: 100,
  reportingUnit: 'sample precincts',
  candidates: [
    { name: 'Sample candidate A', party: 'D', votes: 26000 + index * 2417 },
    { name: 'Sample candidate B', party: 'R', votes: 24400 + index * 3873 },
    { name: 'Sample write-ins', party: 'Other', votes: 373 + index * 32 },
  ],
}]));
