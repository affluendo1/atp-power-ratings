# ATP Power Ratings

An unofficial professional-tennis analytics project, built as the pro-tour sibling of BRTA Power Ratings.

## Current stage: infrastructure

The static app is wired for **ATP singles knockout tournaments** but intentionally contains no invented players, matches or rankings. It provides:

- a professional player-rankings shell;
- event and knockout-draw views;
- a result-ledger and Player Lab home;
- a versioned, empty data contract in `data.js`;
- a transparent methodology placeholder;
- a responsive GitHub Pages-ready layout and favicon.

## Planned data structure

`data.js` will receive three clean collections: `players`, `tournaments` and `matches`. Every match belongs to a tournament and records a round, winner, loser, score and result status. That avoids importing the club-team/fixture structure from the BRTA project into a format where it does not belong.

## Not affiliated

This is an independent analytics project. It is not affiliated with the ATP, Grand Slam tournaments, Tennis Australia, the ITF or any data provider.
