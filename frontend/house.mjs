export const houseFeed = 'https://civicapi.org/api/v2/race/87524';
export const houseSeats = 435;

export function tallyHouse(feed) {
  const updated = Date.parse(feed?.last_updated);
  if (feed?.country !== 'US' || feed.election_type !== 'House of Representatives' ||
      feed.election_scope !== 'General' || feed.election_date?.slice(0, 10) !== '2026-11-03' ||
      feed.test_data !== false || !Number.isFinite(updated)) {
    throw new Error('Unexpected House election feed');
  }

  const districts = Object.values(feed.region_results ?? {});
  if (districts.length !== houseSeats ||
      new Set(districts.map(district => district?.election_id)).size !== houseSeats) {
    throw new Error('Incomplete or duplicate House districts');
  }

  const seats = { democratic: 0, republican: 0, other: 0, uncalled: 0 };
  for (const district of districts) {
    if (district.type !== 'Congressional District' || !Number.isSafeInteger(district.election_id) ||
        !Array.isArray(district.candidates) ||
        district.candidates.some(candidate => typeof candidate?.winner !== 'boolean')) {
      throw new Error('Invalid House district');
    }
    const winners = district.candidates.filter(candidate => candidate.winner);
    if (winners.length > 1 || (winners.length && typeof winners[0].party !== 'string')) {
      throw new Error('Invalid House race call');
    }
    const party = winners[0]?.party.trim().toLowerCase();
    if (!winners.length) seats.uncalled++;
    else if (party === 'democratic') seats.democratic++;
    else if (party === 'republican') seats.republican++;
    else seats.other++;
  }
  return { seats, updated };
}
