/*
 * Data contract for the upcoming professional-tour import.
 * Keep real input records outside the UI code so model, source and display can evolve independently.
 */
window.ATP_RATINGS_DATA = {
  meta: {
    sport: 'tennis',
    circuit: 'ATP',
    scope: 'singles main draws',
    latestEvent: null,
    updatedAt: null,
    schemaVersion: 1
  },
  players: [],
  tournaments: [],
  matches: []
};

/*
Tournament shape: { id, name, level, season, startDate, endDate, city, country, surface, indoor, drawSize }
Player shape:     { id, name, countryCode, handedness, birthDate }
Match shape:      { id, tournamentId, round, matchNumber, winnerId, loserId, score, status, winnerSeed, loserSeed }
status: completed | retirement | walkover | cancelled
*/
