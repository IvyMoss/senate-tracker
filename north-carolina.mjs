export const electionDate = '2026-11-03';
export const sourceUrl = 'https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/results_pct_20261103.zip';

export function parseNorthCarolina(tsv, date = electionDate) {
  const [year, month, day] = date.split('-');
  const expectedDate = `${month}/${day}/${year}`;
  const [header, ...rows] = tsv.split(/\r?\n/);
  const fields = header.split('\t').map(field => field.trim().toLowerCase());
  const required = ['county', 'election date', 'precinct', 'contest group id', 'contest type',
    'contest name', 'choice', 'choice party', 'vote for', 'total votes', 'real precinct'];
  const columns = required.map(field => fields.indexOf(field));
  if (columns.includes(-1)) throw new Error('Unexpected North Carolina results header');

  const candidates = new Map();
  const seen = new Set();
  const groups = new Set();
  for (const row of rows) {
    if (!row.trim()) continue;
    const cells = row.split('\t');
    const [county, election, precinct, group, type, contest, name, partyCode, voteFor, count, real] =
      columns.map(index => cells[index]?.trim());
    if (election !== expectedDate) throw new Error('Unexpected North Carolina election date');
    if (contest !== 'US SENATE') continue;
    if (!county || !precinct || !group || !name || type !== 'S' || voteFor !== '1' ||
        !['Y', 'N'].includes(real) || !/^\d+$/.test(count) || !Number.isSafeInteger(Number(count))) {
      throw new Error('Invalid North Carolina Senate row');
    }
    groups.add(group);
    const key = JSON.stringify([county, precinct, real, name]);
    if (seen.has(key)) throw new Error('Duplicate North Carolina Senate row');
    seen.add(key);
    const party = ({ DEM: 'D', REP: 'R' })[partyCode] ?? (partyCode || 'Other');
    const previous = candidates.get(name);
    if (previous && previous.party !== party) throw new Error('Inconsistent North Carolina party code');
    const votes = (previous?.votes ?? 0) + Number(count);
    if (!Number.isSafeInteger(votes)) throw new Error('North Carolina vote total exceeds safe range');
    candidates.set(name, { name, party, votes });
  }
  if (groups.size !== 1 || candidates.size < 2) throw new Error('Expected one statewide North Carolina Senate contest');
  const totals = [...candidates.values()];
  const hasVotes = totals.some(candidate => candidate.votes > 0);
  return {
    status: hasVotes ? 'reporting' : 'unresolved',
    candidates: totals.map(candidate => ({ ...candidate, votes: hasVotes ? candidate.votes : null })),
  };
}

// NCSBE publishes a single-entry ZIP with a raw DEFLATE payload.
export async function parseNorthCarolinaArchive(archive) {
  const limit = 64 * 1024 * 1024;
  const bytes = new Uint8Array(archive);
  const zip = new DataView(archive);
  const u16 = offset => zip.getUint16(offset, true);
  const u32 = offset => zip.getUint32(offset, true);
  const end = bytes.length - 22;
  if (end < 0 || bytes.length > 16 * 1024 * 1024 ||
      u32(end) !== 0x06054b50 || u16(end + 4) || u16(end + 6) ||
      u16(end + 8) !== 1 || u16(end + 10) !== 1 || u16(end + 20)) {
    throw new Error('Unexpected North Carolina ZIP directory');
  }
  const entry = u32(end + 16);
  if (entry + 46 > end || u32(entry) !== 0x02014b50 ||
      u16(entry + 10) !== 8 || (u16(entry + 8) & 1)) {
    throw new Error('Unsupported North Carolina ZIP entry');
  }
  const name = 'results_pct_20261103.txt';
  const size = u32(entry + 24);
  const local = u32(entry + 42);
  if (u16(entry + 28) !== name.length ||
      new TextDecoder().decode(bytes.subarray(entry + 46, entry + 46 + name.length)) !== name ||
      size > limit || local + 30 > entry || u32(local) !== 0x04034b50) {
    throw new Error('Unexpected North Carolina results file');
  }
  const start = local + 30 + u16(local + 26) + u16(local + 28);
  const stop = start + u32(entry + 20);
  if (stop > entry) throw new Error('Truncated North Carolina ZIP payload');
  const stream = new Blob([bytes.subarray(start, stop)]).stream()
    .pipeThrough(new DecompressionStream('deflate-raw'));
  const reader = stream.getReader();
  const output = new Uint8Array(size);
  let written = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (written + value.length > size) throw new Error('Unexpected decompressed size');
      output.set(value, written);
      written += value.length;
    }
  } finally {
    await reader.cancel();
  }
  if (written !== size) throw new Error('Truncated North Carolina results file');
  let tsv;
  try {
    tsv = new TextDecoder('utf-8', { fatal: true }).decode(output);
  } catch {
    tsv = new TextDecoder('windows-1252').decode(output);
  }
  return { ...parseNorthCarolina(tsv), sourceUrl };
}

export async function fetchNorthCarolina() {
  const response = await fetch(sourceUrl, { signal: AbortSignal.timeout(30_000) });
  if (!response.ok) throw new Error('North Carolina archive unavailable');
  return parseNorthCarolinaArchive(await response.arrayBuffer());
}
