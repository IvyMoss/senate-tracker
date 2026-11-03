import { fetchNorthCarolina } from './north-carolina.mjs';
import { ohioFeed, parseOhio } from './ohio.mjs';
import { pollResults } from './results.mjs';
import { races, defaults, additional, scenario, balance, summarize, resolvedParty, testRecords } from './elections.mjs';

const byId = id => document.getElementById(id);
let officialRecords = {};
let publishedRecords = {};
const browserRecords = {};
let refreshFailed = false;
const number = new Intl.NumberFormat('en-US');
const time = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' });
const partyClass = { D: 'dem', R: 'rep' };
const statuses = {
  reporting: 'Reporting', leading: 'Leading', unresolved: 'Unresolved',
  runoff_required: 'Runoff required', ranked_choice_pending: 'First-choice totals · Ranked-choice tabulation pending',
  final_unofficial: 'Final unofficial', certified: 'Certified',
};

function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (className) node.className = className;
  return node;
}

function score(label, value, className) {
  const node = element('div', undefined, 'score ' + (className ?? ''));
  node.append(element('strong', value), element('span', label));
  return node;
}

function renderBalance() {
  const result = balance(officialRecords);
  byId('balance-scores').replaceChildren(
    score('Democratic caucus', result.democratic, 'dem'),
    score('Republican', result.republican, 'rep'),
    score('Tracked seats unresolved', result.unresolved),
  );
  const segments = [
    [result.baseD, 'dem'], [result.gainedD, 'dem secured'], [result.unresolved, 'pending'],
    [result.gainedR, 'rep secured'], [result.baseR, 'rep'],
  ];
  byId('seat-chart').replaceChildren(...segments.filter(([seats]) => seats > 0).map(([seats, style]) => {
    const segment = element('span', undefined, style);
    segment.style.width = seats + '%';
    return segment;
  }));
  byId('balance-note').textContent =
    `${Math.max(0, 51 - result.democratic)} Democratic seats needed from unresolved races for 51. ` +
    `${result.baseD + result.baseR} seats assumed outside the tracker · ${result.gainedD + result.gainedR} certified tracked seats.`;
}

function renderFeed() {
  const demo = byId('demo').checked;
  const records = Object.values(demo ? testRecords : officialRecords);
  const latest = Math.max(...records.map(record => Date.parse(record.sourceUpdatedAt ?? '') || -Infinity));
  const timestamp = Number.isFinite(latest) ? time.format(latest) : 'unavailable';
  const reporting = records.filter(record => record.candidates.some(candidate => candidate.votes !== null)).length;
  const status = demo
    ? `TEST DATA · ${records.length} simulated returns · Sample update ${timestamp}`
    : `${refreshFailed ? 'Refresh failed' : reporting ? 'Published official returns' : 'Awaiting official returns'} · ` +
      `${reporting} of 9 reporting · ` +
      `Latest source update ${timestamp}`;
  const feed = byId('feed-status');
  if (feed.textContent !== status) feed.textContent = status;
}

function renderRaces() {
  const demo = byId('demo').checked;
  const records = demo ? testRecords : officialRecords;
  const grid = byId('race-grid');
  const open = new Set([...grid.querySelectorAll('details[open]')].map(node => node.id));
  const items = races.map(race => {
    const record = records[race.state];
    return { race, record, totals: summarize(record?.candidates ?? []) };
  });
  const sort = byId('sort').value;
  const progress = record => record?.reportingPercent != null ? record.reportingPercent / 100
    : record?.reportingTotal > 0 ? record.reporting / record.reportingTotal : -1;
  if (sort === 'state') items.sort((a, b) => a.race.name.localeCompare(b.race.name));
  if (sort === 'margin') items.sort((a, b) => (a.totals.points ?? Infinity) - (b.totals.points ?? Infinity));
  if (sort === 'progress') items.sort((a, b) => progress(b.record) - progress(a.record));
  if (sort === 'updated') items.sort((a, b) => (b.record?.sourceUpdatedAt ?? '').localeCompare(a.record?.sourceUpdatedAt ?? ''));
  renderFeed();
  grid.replaceChildren(...items.map(({ race, record, totals }) => {
    const card = element('article', undefined, 'race');
    const heading = element('div', undefined, 'race-heading');
    heading.append(element('span', race.state, 'badge'), element('h3', race.name));
    card.append(heading, element('p', 'U.S. Senate · General election', 'note'));
    const status = statuses[record?.status] ?? 'Awaiting results';
    card.append(element('p', (demo ? 'TEST MODE · ' : '') + status, 'status'));
    if (totals.ranked.length) {
      const list = element('ul', undefined, 'candidates');
      for (const candidate of totals.ranked) {
        const row = element('div', undefined, 'candidate-row');
        const share = candidate.share == null ? '—' : candidate.share.toFixed(1) + '%';
        row.append(element('span', `${candidate.name} (${candidate.party})`, partyClass[candidate.party]),
          element('span', `${candidate.votes == null ? '—' : number.format(candidate.votes)} · ${share}`));
        const item = element('li');
        item.append(row);
        if (candidate.share != null) {
          const track = element('span', undefined, 'vote-track');
          track.setAttribute('aria-hidden', 'true');
          const fill = element('span', undefined, 'vote-fill ' + (partyClass[candidate.party] ?? ''));
          fill.style.width = candidate.share + '%';
          track.append(fill);
          item.append(track);
        }
        list.append(item);
      }
      card.append(list);
      if (totals.margin !== null) {
        const lead = totals.margin === 0 ? 'Tied' : `${totals.ranked[0].name} leads`;
        card.append(element('p', `${lead} · ${number.format(totals.margin)} votes · ${totals.points.toFixed(1)} pp`, 'note'));
      }
    } else {
      card.append(element('p', 'Candidate totals unavailable', 'note'));
    }
    card.append(element('p', record?.reportingPercent != null
      ? `${number.format(record.reportingPercent)}% of polling locations reporting`
      : progress(record) >= 0
      ? `${record.reporting} of ${record.reportingTotal} ${record.reportingUnit} reporting`
      : 'Reporting progress unavailable', 'note'));
    const details = element('details');
    details.id = 'details-' + race.state;
    details.open = open.has(details.id);
    details.append(element('summary', `${race.name} race details`),
      element('p', 'Source authority · ' + race.authority, 'note'),
      element('p', totals.total === null ? 'Total votes unavailable' : 'Total votes · ' + number.format(totals.total), 'note'),
      element('p', record?.synthetic ? 'Synthetic fixture · No official source timestamp' :
        record?.sourceUpdatedAt ? 'Source update · ' + time.format(new Date(record.sourceUpdatedAt)) :
        'Official source timestamp unavailable', 'note'),
      element('p', 'County breakdowns and history unavailable', 'note'));
    const source = element('a', 'Official election source', 'official');
    source.href = race.url;
    card.append(details, source);
    return card;
  }));
}

const inputs = {};
for (const [legend, states] of [
  ['Democratic defenses', races.slice(0, 2)], ['Initial pickup', races.slice(2, 3)], ['Additional pickups', additional],
]) {
  const group = element('fieldset');
  const options = element('div', undefined, 'options');
  group.append(element('legend', legend), options);
  for (const race of states) {
    const label = element('label');
    const input = element('input');
    input.type = 'checkbox';
    input.checked = defaults[race.state];
    inputs[race.state] = input;
    input.addEventListener('change', renderScenario);
    label.append(input, (race.incumbent === 'D' ? ' Retain ' : ' Flip ') + race.name);
    options.append(label);
  }
  byId('assumptions').append(group);
}

function renderScenario() {
  const result = scenario(Object.fromEntries(Object.entries(inputs).map(([state, input]) => [state, input.checked])));
  byId('scenario-scores').replaceChildren(score('Democratic caucus', result.democratic, 'dem'),
    score('Republican', result.republican, 'rep'), score('Seats needed for 51', result.needed));
  const change = result.net > 0 ? '+' + result.net : String(result.net);
  const control = result.needed === 0 ? 'Democratic majority' : result.democratic === 50 ? '50–50 Senate' : 'Republican majority';
  byId('scenario-message').textContent = `${control} · Democratic net change ${change}`;
  byId('flip-message').textContent = result.needed > result.flipsRemaining
    ? 'The six-state list cannot supply enough flips under these selections.'
    : `${result.needed} more flips needed from the six-state list, holding other selections fixed.`;
}

byId('reset').addEventListener('click', () => {
  for (const [state, input] of Object.entries(inputs)) input.checked = defaults[state];
  byId('import-message').textContent = '';
  renderScenario();
});
byId('resolved').addEventListener('click', () => {
  const unresolved = [];
  for (const { state } of races) {
    const party = resolvedParty(officialRecords[state]);
    if (party) inputs[state].checked = party === 'D';
    else unresolved.push(state);
  }
  byId('import-message').textContent = unresolved.length
    ? 'Still hypothetical for unresolved races · ' + unresolved.join(', ')
    : 'All tracked outcomes applied.';
  renderScenario();
});
byId('theme').addEventListener('click', () => {
  const light = document.documentElement.dataset.theme === 'dark';
  document.documentElement.dataset.theme = light ? 'light' : 'dark';
  byId('theme').textContent = light ? 'Dark mode' : 'Light mode';
});
byId('sort').addEventListener('change', renderRaces);
byId('demo').addEventListener('change', renderRaces);
renderBalance();
renderRaces();
renderScenario();

function updateRecords() {
  const records = { ...publishedRecords };
  for (const [state, record] of Object.entries(browserRecords)) {
    const published = records[state];
    if (published?.status === 'certified') continue;
    if (published?.sourceUpdatedAt && published.sourceUpdatedAt > (record.sourceUpdatedAt ?? '')) continue;
    if (record.status === 'unresolved' && published?.candidates.some(candidate => candidate.votes !== null)) continue;
    records[state] = record;
  }
  const changed = JSON.stringify(records) !== JSON.stringify(officialRecords);
  officialRecords = records;
  if (changed) {
    renderBalance();
    if (!byId('demo').checked) renderRaces();
  }
  renderFeed();
}

pollResults(records => {
  publishedRecords = records;
  refreshFailed = false;
  updateRecords();
}, () => {
  refreshFailed = true;
  renderFeed();
});

async function refreshNorthCarolina() {
  try {
    const record = await fetchNorthCarolina();
    if (record.status === 'reporting' || browserRecords.NC?.status !== 'reporting') {
      browserRecords.NC = record;
      updateRecords();
    }
    byId('nc-refresh').textContent = '';
  } catch {
    byId('nc-refresh').textContent = 'North Carolina archive unavailable. Showing the last available data.';
  } finally {
    setTimeout(refreshNorthCarolina, 5 * 60_000);
  }
}

byId('ohio-download').href = ohioFeed;
byId('ohio-import').addEventListener('change', async event => {
  const input = event.currentTarget;
  const file = input.files[0];
  if (!file) return;
  input.disabled = true;
  const status = byId('ohio-import-status');
  try {
    if (file.size > 32 * 1024 * 1024) throw new Error('Ohio XML file is too large');
    const record = parseOhio(await file.text());
    const previous = officialRecords.OH;
    if (previous?.status === 'certified' ||
        (previous?.sourceUpdatedAt && previous.sourceUpdatedAt > record.sourceUpdatedAt) ||
        (record.status === 'unresolved' && previous?.status === 'reporting')) {
      throw new Error('Kept the Ohio result already displayed');
    }
    browserRecords.OH = record;
    updateRecords();
    status.textContent = 'Ohio report loaded for this session.';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    input.value = '';
    input.disabled = false;
  }
});

refreshNorthCarolina();
