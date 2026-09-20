# ATP Power Ratings

An independent, ATP-only professional-singles analytics project. It is not affiliated with the ATP, ITF, Grand Slam tournaments, Laver Cup, Davis Cup, United Cup, Hopman Cup or the data providers.

## Coverage

The rolling database starts three years before each sync date and includes only men's singles:

- ATP Tour, Grand Slams and ATP Finals;
- ATP Challenger Tour;
- ATP Tour qualifying;
- Davis Cup and United Cup when present in the ATP feed;
- Laver Cup and Hopman Cup men's singles through the project’s verified supplementary dataset.

No WTA file is ever selected. Doubles, women’s singles and mixed doubles are excluded from the rating model.

## Sources

`sync_atp.py` discovers files from the TennisMyLife public data index at `https://stats.tennismylife.org/api/data-files`. That provider publishes separate ATP Tour, Challenger and ATP qualifying files, refreshed daily. The importer stores the exact source filename and URL on every match row.

`data/manual/special_events.csv` adds historical men's singles for Laver Cup and Hopman Cup, which are not reliably represented in the ATP stream. Every row contains its official result-page source URL. It is deliberately small, reviewed and plainly identifiable rather than silently pretending those competitions do not exist.

## ATP V1 rating model

The BRTA V3 scoreline model is adapted for professional tennis:

- game probability: `p(i,j) = logistic((theta_i - theta_j) / 0.75)`;
- one scoreline likelihood only: `g_w log(p) + g_l log(1-p)`;
- 300-day exponential half-life, within a rolling three-year window;
- L2 regularisation of `5/2 * sum(theta_i^2)`;
- display: `Power = 1500 + 600 theta`;
- centred Laplace approximation for rating uncertainty;
- eight completed rating-eligible matches required for an established entry.

### Best-of-five and match tiebreaks

Conventional set games from best-of-three and best-of-five are retained. A five-set match does **not** become several independent matches: its game likelihood is capped at 28 game-equivalents. Match-tiebreak points such as `[10-8]` decide the result but are not treated as conventional games. Walkovers and retirements remain in the public result ledger but are excluded from scoreline ratings.

## Daily automation

`.github/workflows/sync-atp.yml` runs at **7:22 am Australia/Melbourne**, can be dispatched manually, and runs after changes to its pipeline files. It:

1. downloads and validates every eligible ATP-only source file;
2. deduplicates, normalises and writes the rolling match ledger;
3. compares it with the previous ledger for additions and corrections;
4. recalculates ratings and static site data;
5. commits updated data, status and rankings to `main`;
6. publishes the exact result summary in the workflow run.

### Email reports

GitHub Actions cannot safely invent an email account. The workflow is ready to send each finished report through Resend once these **repository secrets** are set:

- `RESEND_API_KEY`
- `SYNC_REPORT_TO`
- `SYNC_REPORT_FROM`

Without all three, the sync and site update still run and the workflow explicitly reports that email was skipped. Never put a mail key or email address in this public repository.

## Site analytics

The static site keeps its landing payload compact and loads detailed JSON only when a visitor opens a player or event. Each completed sync publishes:

- **Player Lab** profiles: current Power/uncertainty, surface and event-level records, recent results, best wins, toughest losses, and a clearly-labelled smoothed match-performance trend;
- **Matchup Lab**: a best-of-three or best-of-five match-probability conversion from the game model, plus head-to-head and surface context. Surface form is deliberately shown separately until it has passed validation as a model adjustment;
- **Tournament Centre / Knockout Draw**: a standalone event page and round-by-round result reconstruction for every imported event;
- **Daily Round Centre**: the latest source-date results, featured events, and the exact additions/corrections from the current sync;
- **Model Health**: internal-fit diagnostics, scoreline error by surface, status counts, source-file traceability and import-quality checks.

The model-health figures are explicitly in-sample diagnostics, not a claim of out-of-sample forecasting performance. A time-split backtest is intentionally the next validation upgrade.

## Development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python sync_atp.py
python generate_site_data.py
```
