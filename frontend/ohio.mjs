export const ohioFeed = 'https://liveresults.ohiosos.gov/Api/v1/download?filename=VSSC1622XmlFileBlob';

const namespace = 'http://grouper.ieee.org/groups/1622/groups/2/V1/1622_2-election_results_reporting.xsd';

function only(elements, label) {
  if (elements.length !== 1) throw new Error('Expected one Ohio ' + label);
  return elements[0];
}

export function parseOhio(xml) {
  if (xml.length > 32 * 1024 * 1024 || /<!DOCTYPE/i.test(xml)) {
    throw new Error('Unsupported Ohio XML file');
  }
  const report = new DOMParser().parseFromString(xml, 'application/xml').documentElement;
  if (report.localName !== 'ElectionReport' || report.namespaceURI !== namespace ||
      report.getAttribute('IssuerAbbreviation') !== 'OH') {
    throw new Error('Expected an Ohio election report');
  }
  if (report.getAttribute('IsTest') === 'true' || report.getAttribute('IsTest') === '1') {
    throw new Error('Ohio marked this file as test data');
  }
  const elements = (parent, name) => [...parent.getElementsByTagNameNS(namespace, name)];
  const election = only(elements(report, 'Election').filter(node =>
    node.getAttribute('Date') === '2026-11-03' && node.getAttribute('Type') === 'General'), '2026 general election');
  const state = only(elements(report, 'GpUnit').filter(node => node.getAttribute('Type') === 'State'), 'statewide unit');
  const stateId = state.getAttribute('ObjectId');
  const contest = only(elements(election, 'Contest').filter(node =>
    node.getAttribute('Name') === 'U.S. Senator' &&
    elements(node, 'JurisdictionalScopeId').some(scope => scope.textContent.trim() === stateId)), 'statewide U.S. Senate contest');
  const candidates = elements(election, 'Candidate');
  const parties = elements(report, 'Party');
  const seen = new Set();
  const totals = elements(contest, 'BallotSelection').map(selection => {
    const id = only(elements(selection, 'CandidateId'), 'candidate reference').textContent.trim();
    if (!id || seen.has(id)) throw new Error('Duplicate or missing Ohio candidate ID');
    seen.add(id);
    const candidate = only(candidates.filter(node => node.getAttribute('ObjectId') === id), 'candidate');
    const name = only(elements(candidate, 'BallotName'), 'ballot name').textContent.trim();
    const partyId = elements(candidate, 'PartyId')[0]?.textContent.trim();
    const code = partyId
      ? only(parties.filter(node => node.getAttribute('ObjectId') === partyId), 'party').getAttribute('Abbreviation')
      : 'Other';
    const count = only(elements(selection, 'VoteCounts').filter(node =>
      node.getAttribute('Type') === 'Total' &&
      elements(node, 'GpUnitId').some(unit => unit.textContent.trim() === stateId)), 'statewide candidate total');
    const value = count.getAttribute('Count');
    const votes = Number(value);
    if (!name || !code || !/^\d+$/.test(value ?? '') || !Number.isSafeInteger(votes)) {
      throw new Error('Invalid Ohio candidate result');
    }
    return { name, party: ({ DEM: 'D', REP: 'R' })[code] ?? code, votes };
  });
  if (totals.length < 2) throw new Error('Incomplete Ohio Senate contest');
  const timestamp = Date.parse(report.getAttribute('GeneratedDate'));
  if (!Number.isFinite(timestamp)) throw new Error('Missing Ohio publication timestamp');
  const hasVotes = totals.some(candidate => candidate.votes > 0);
  return {
    status: hasVotes ? 'reporting' : 'unresolved',
    sourceUpdatedAt: new Date(timestamp).toISOString(),
    candidates: totals.map(candidate => ({ ...candidate, votes: hasVotes ? candidate.votes : null })),
  };
}
