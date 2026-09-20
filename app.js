(() => {
  const data = window.ATP_RATINGS_DATA || {};
  const $ = (selector) => document.querySelector(selector);
  const playerById = new Map((data.rankings || []).map((player) => [player.playerId, player]));
  const jsonCache = new Map();
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const fmt = (value) => value === null || value === undefined || value === '' ? '—' : Number.isFinite(Number(value)) ? Number(value).toLocaleString() : String(value);
  const pct = (value) => value === null || value === undefined ? '—' : `${Math.round(Number(value) * 100)}%`;
  const date = (value) => value ? new Intl.DateTimeFormat(undefined, {dateStyle:'medium'}).format(new Date(`${value}T00:00:00`)) : '—';

  async function loadJson(ref) {
    if (!jsonCache.has(ref)) {
      jsonCache.set(ref, fetch(`data/site/${ref}`).then((response) => {
        if (!response.ok) throw new Error(`Could not load ${ref}`);
        return response.json();
      }));
    }
    return jsonCache.get(ref);
  }

  function setView(name) {
    const safeName = document.querySelector(`[data-panel="${name}"]`) ? name : 'today';
    document.querySelectorAll('[data-panel]').forEach((panel) => panel.classList.toggle('is-visible', panel.dataset.panel === safeName));
    document.querySelectorAll('[data-view]').forEach((link) => link.classList.toggle('active', link.dataset.view === safeName));
    if (window.location.hash !== `#${safeName}`) history.replaceState(null, '', `#${safeName}`);
    if (safeName === 'today') renderRoundCentre();
    if (safeName === 'health') renderHealth();
  }

  function hydrateStatus() {
    const meta = data.meta || {};
    document.querySelectorAll('[data-stat="players"]').forEach((node) => node.textContent = fmt(meta.players));
    document.querySelectorAll('[data-stat="matches"]').forEach((node) => node.textContent = fmt(meta.matches));
    document.querySelectorAll('[data-stat="events"]').forEach((node) => node.textContent = fmt(meta.events));
    document.querySelectorAll('[data-stat="event"]').forEach((node) => node.textContent = meta.latestEvent || '—');
    document.querySelectorAll('[data-stat="updated"]').forEach((node) => node.textContent = meta.updatedAt ? new Date(meta.updatedAt).toLocaleString() : '—');
    document.querySelectorAll('[data-stat="window"]').forEach((node) => node.textContent = date(meta.coverageStart));
    document.querySelectorAll('[data-stat="new-matches"]').forEach((node) => node.textContent = fmt(meta.newMatches));
    $('#scope-status').textContent = meta.updatedAt ? `Checked ${new Date(meta.updatedAt).toLocaleDateString()}` : 'Awaiting first sync';
  }

  function cell(value, className = '') {
    const td = document.createElement('td');
    td.textContent = value;
    if (className) td.className = className;
    return td;
  }

  function renderTable(id, rows, makeRow, columns) {
    const target = $(`#${id}`);
    if (!target) return;
    target.replaceChildren();
    if (!rows.length) {
      const row = document.createElement('tr');
      const empty = cell('No matching published data.', 'loading-cell');
      empty.colSpan = columns;
      row.append(empty);
      target.append(row);
      return;
    }
    rows.forEach((item) => target.append(makeRow(item)));
  }

  function playerButton(player, label = player.player) {
    const button = document.createElement('button');
    button.className = 'player-link';
    button.textContent = label;
    button.addEventListener('click', () => openPlayer(player.playerId));
    return button;
  }

  function renderRankings() {
    const search = $('#ranking-search').value.trim().toLowerCase();
    const provisional = $('#show-provisional').checked;
    const rows = (data.rankings || []).filter((player) => (provisional || player.qualified) && player.player.toLowerCase().includes(search));
    renderTable('rankings-table', rows, (item) => {
      const row = document.createElement('tr');
      if (!item.qualified) row.className = 'provisional-row';
      const name = document.createElement('td'); name.append(playerButton(item));
      row.append(cell(item.qualified ? item.rank : '—'), name, cell(item.rating), cell(`${item.wins}–${item.losses}`), cell(item.matches), cell(`${item.lo}–${item.hi}`));
      return row;
    }, 6);
  }

  function populatePlayers() {
    const options = (data.rankings || []).map((player) => `<option value="${escapeHtml(player.playerId)}">${escapeHtml(player.player)} · ${player.rating}</option>`).join('');
    ['#player-select', '#matchup-a', '#matchup-b'].forEach((selector) => $(selector).innerHTML = options);
    if (data.rankings?.length > 1) $('#matchup-b').selectedIndex = 1;
  }

  function matchRow(match) {
    const result = match.won ? 'W' : 'L';
    return `<tr><td>${date(match.date)}</td><td><span class="result-badge ${match.won ? 'win' : 'loss'}">${result}</span> <button class="player-link" data-player-id="${escapeHtml(match.opponentId)}">${escapeHtml(match.opponent)}</button></td><td>${escapeHtml(match.score)}</td><td>${escapeHtml(match.round || '—')}</td><td>${escapeHtml(match.event)}</td><td>${fmt(match.performancePower)}</td></tr>`;
  }

  function recordCards(records) {
    const entries = Object.entries(records || {});
    if (!entries.length) return '<p class="muted-copy">No completed scorelines available.</p>';
    return entries.map(([name, value]) => `<article class="micro-card"><span>${escapeHtml(name || 'Unknown')}</span><strong>${value.wins}–${value.losses}</strong><small>${fmt(value.winPct)}% wins · ${value.gamesFor}–${value.gamesAgainst} games</small></article>`).join('');
  }

  function trendChart(trend) {
    if (!trend?.length) return '<p class="muted-copy">Not enough completed results for a trend.</p>';
    const width = 680, height = 190, pad = 25;
    const values = trend.map((item) => item.power);
    const min = Math.min(...values) - 30, max = Math.max(...values) + 30;
    const range = Math.max(max - min, 1);
    const points = trend.map((item, index) => `${pad + index * ((width - 2 * pad) / Math.max(trend.length - 1, 1))},${height - pad - ((item.power - min) / range) * (height - 2 * pad)}`).join(' ');
    const labels = trend.filter((_, index) => index === 0 || index === trend.length - 1 || index % 4 === 0).map((item, index) => `<text x="${pad + index * 0}" y="0"></text>`).join('');
    return `<svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Smoothed match-performance Power trend"><line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}"/><line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}"/><polyline points="${points}"/><text x="${pad}" y="${height - 5}">${escapeHtml(trend[0].month)}</text><text x="${width - pad - 48}" y="${height - 5}">${escapeHtml(trend[trend.length - 1].month)}</text><text x="${pad + 5}" y="${pad + 10}">${Math.round(max)}</text><text x="${pad + 5}" y="${height - pad - 5}">${Math.round(min)}</text>${labels}</svg>`;
  }

  async function openPlayer(playerId) {
    const player = playerById.get(playerId);
    if (!player) return;
    $('#player-select').value = playerId;
    setView('players');
    const target = $('#player-content');
    target.innerHTML = '<section class="panel loading-panel">Opening Player Lab…</section>';
    try {
      const profile = await loadJson(player.profileRef);
      const p = profile.player;
      target.innerHTML = `<section class="player-hero panel"><div><p class="eyebrow">#${p.rank} · ${p.qualified ? 'ESTABLISHED' : 'PROVISIONAL'}</p><h2>${escapeHtml(p.player)}</h2><p>${p.wins}–${p.losses} across ${p.matches} rating-eligible matches. Uncertainty: ${p.lo}–${p.hi}.</p></div><div class="power-orb"><span>POWER</span><strong>${p.rating}</strong><small>±${p.se}</small></div></section>
      <section class="profile-grid"><article class="panel"><h2>Surface record</h2><div class="micro-grid">${recordCards(profile.surfaceRecords)}</div></article><article class="panel"><h2>Level record</h2><div class="micro-grid">${recordCards(profile.levelRecords)}</div></article></section>
      <section class="panel"><h2>Performance trend</h2>${trendChart(profile.trend)}<p class="muted-copy">${escapeHtml(profile.trendNote)}</p></section>
      <section class="profile-grid"><article class="panel"><h2>Best wins by opponent Power</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>Opponent</th><th>Score</th><th>Round</th><th>Event</th><th>Perf.</th></tr></thead><tbody>${profile.bestWins.map(matchRow).join('') || '<tr><td colspan="6">No results.</td></tr>'}</tbody></table></div></article><article class="panel"><h2>Toughest losses by opponent Power</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>Opponent</th><th>Score</th><th>Round</th><th>Event</th><th>Perf.</th></tr></thead><tbody>${profile.toughLosses.map(matchRow).join('') || '<tr><td colspan="6">No results.</td></tr>'}</tbody></table></div></article></section>
      <section class="panel"><h2>Recent completed matches</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>Opponent</th><th>Score</th><th>Round</th><th>Event</th><th>Perf.</th></tr></thead><tbody>${profile.recentMatches.map(matchRow).join('') || '<tr><td colspan="6">No results.</td></tr>'}</tbody></table></div></section>`;
      target.querySelectorAll('[data-player-id]').forEach((button) => button.addEventListener('click', () => openPlayer(button.dataset.playerId)));
    } catch (error) {
      target.innerHTML = `<section class="panel empty-panel"><h2>Profile unavailable</h2><p>${escapeHtml(error.message)}</p></section>`;
    }
  }

  function setWinProbability(gameP) {
    const p = Math.min(Math.max(gameP, 1e-8), 1 - 1e-8), q = 1 - p;
    let early = 0;
    for (let losses = 0; losses < 5; losses += 1) {
      let comb = 1;
      for (let i = 1; i <= losses; i += 1) comb *= (5 + i) / i;
      early += comb * p ** 6 * q ** losses;
    }
    return early + 252 * p ** 5 * q ** 5 * (p ** 2 + 2 * p * q * p);
  }

  function matchProbability(a, b, format) {
    const gameP = 1 / (1 + Math.exp(-((a.rating - b.rating) / 600) / (data.model?.gameScale || .75)));
    const setP = setWinProbability(gameP), q = 1 - setP;
    return format >= 5 ? setP ** 3 + 3 * setP ** 3 * q + 6 * setP ** 3 * q ** 2 : setP ** 2 + 2 * setP ** 2 * q;
  }

  async function renderMatchup() {
    const a = playerById.get($('#matchup-a').value), b = playerById.get($('#matchup-b').value);
    const format = Number($('#matchup-format').value);
    const target = $('#matchup-content');
    if (!a || !b || a.playerId === b.playerId) { target.innerHTML = '<section class="panel empty-panel"><h2>Choose two different players.</h2></section>'; return; }
    const chance = matchProbability(a, b, format);
    target.innerHTML = '<section class="panel loading-panel">Calculating matchup context…</section>';
    try {
      const [aProfile, bProfile] = await Promise.all([loadJson(a.profileRef), loadJson(b.profileRef)]);
      const h2h = (aProfile.headToHead || []).find((entry) => entry.opponentId === b.playerId);
      const h2hText = h2h ? `${h2h.wins}–${h2h.losses} for ${a.player} (${h2h.matches} completed meetings)` : 'No completed head-to-head in the three-year ledger.';
      target.innerHTML = `<section class="matchup-card panel"><div class="matchup-player"><span>PLAYER A</span><strong>${escapeHtml(a.player)}</strong><small>${a.rating} Power · ${a.wins}–${a.losses}</small></div><div class="matchup-odds"><span>MODEL BASELINE</span><strong>${pct(chance)}</strong><small>${format === 5 ? 'best of five' : 'best of three'} win chance</small></div><div class="matchup-player right"><span>PLAYER B</span><strong>${escapeHtml(b.player)}</strong><small>${b.rating} Power · ${b.wins}–${b.losses}</small></div></section>
      <section class="profile-grid"><article class="panel"><h2>Head-to-head</h2><p>${escapeHtml(h2hText)}</p></article><article class="panel"><h2>Surface context</h2><p>This V1 probability is a global model baseline. Surface records are displayed in Player Lab but are not yet turned into an unvalidated adjustment.</p></article></section>`;
    } catch (error) { target.innerHTML = `<section class="panel empty-panel"><h2>Matchup unavailable</h2><p>${escapeHtml(error.message)}</p></section>`; }
  }

  function renderTournaments() {
    const query = $('#event-search').value.trim().toLowerCase(), type = $('#event-type-filter').value;
    const rows = (data.tournaments || []).filter((event) => (!query || `${event.name} ${event.type}`.toLowerCase().includes(query)) && (!type || event.type === type)).slice(0, 250);
    renderTable('tournaments-table', rows, (item) => {
      const row = document.createElement('tr');
      const eventName = document.createElement('td');
      const button = document.createElement('button'); button.className = 'player-link'; button.textContent = item.name;
      button.addEventListener('click', () => openDraw(item.detailRef)); eventName.append(button);
      row.append(eventName, cell(item.type), cell(`${item.surface}${item.indoor && item.indoor !== 'N' ? ' · indoor' : ''}`), cell(`${date(item.startDate)} → ${date(item.endDate)}`), cell(item.champion || '—'), cell(item.matches));
      return row;
    }, 6);
  }

  async function openDraw(ref) {
    const event = (data.tournaments || []).find((item) => item.detailRef === ref);
    if (event) $('#draw-event-select').value = ref;
    setView('draw');
    const target = $('#draw-content'); target.innerHTML = '<section class="panel loading-panel">Reconstructing draw rounds…</section>';
    try {
      const detail = await loadJson(ref);
      target.innerHTML = `<section class="event-hero panel"><div><p class="eyebrow">${escapeHtml(detail.type)}</p><h2>${escapeHtml(detail.name)}</h2><p>${date(detail.startDate)} → ${date(detail.endDate)} · ${escapeHtml(detail.surface)} · ${detail.matches} results indexed</p></div><div><span class="muted-copy">Champion</span><strong class="champion-name">${escapeHtml(detail.champion || 'Not resolved')}</strong></div></section><section class="draw-board">${detail.rounds.map((round) => `<article class="draw-column"><h2>${escapeHtml(round.round)}</h2>${round.matches.map((match) => `<div class="draw-match"><span><button class="player-link" data-player-id="${escapeHtml(match.winnerId)}">${escapeHtml(match.winner)}</button></span><b>${escapeHtml(match.score || match.status)}</b><span><button class="player-link" data-player-id="${escapeHtml(match.loserId)}">${escapeHtml(match.loser)}</button></span></div>`).join('')}</article>`).join('')}</section>`;
      target.querySelectorAll('[data-player-id]').forEach((button) => button.addEventListener('click', () => openPlayer(button.dataset.playerId)));
    } catch (error) { target.innerHTML = `<section class="panel empty-panel"><h2>Draw unavailable</h2><p>${escapeHtml(error.message)}</p></section>`; }
  }

  function renderResults() {
    const query = $('#result-search').value.trim().toLowerCase(), status = $('#result-status').value;
    const rows = (data.recentMatches || []).filter((match) => (!query || `${match.event} ${match.winner} ${match.loser}`.toLowerCase().includes(query)) && (!status || match.status === status));
    renderTable('results-table', rows, (item) => {
      const row = document.createElement('tr');
      const winner = document.createElement('td'); winner.append(playerButton(playerById.get(item.winnerId) || {playerId:item.winnerId, player:item.winner}, item.winner));
      const loser = document.createElement('td'); loser.append(playerButton(playerById.get(item.loserId) || {playerId:item.loserId, player:item.loser}, item.loser));
      row.append(cell(date(item.date)), cell(item.event), cell(item.round || '—'), winner, cell(item.score || item.status), loser);
      return row;
    }, 6);
  }

  async function renderRoundCentre() {
    const target = $('#round-centre-content');
    try {
      const centre = await loadJson(data.roundCentreRef || 'round_centre.json');
      target.innerHTML = `<section class="panel centre-note"><strong>Latest source date: ${date(centre.headlineDate)}</strong><span>${fmt(centre.sync.new_matches)} new · ${fmt(centre.sync.corrected_matches)} corrected in the last published check.</span></section><section class="profile-grid"><article class="panel"><h2>Featured events</h2><div class="event-list">${centre.featuredEvents.slice(0, 8).map((event) => `<button class="event-row" data-event-ref="${escapeHtml(event.detailRef)}"><span>${escapeHtml(event.name)}</span><small>${escapeHtml(event.type)} · ${event.matches} matches</small></button>`).join('')}</div></article><article class="panel"><h2>Latest results</h2><div class="result-list">${centre.latestResults.slice(0, 12).map((match) => `<div><small>${date(match.date)} · ${escapeHtml(match.event)}</small><strong>${escapeHtml(match.winner)} def. ${escapeHtml(match.loser)}</strong><span>${escapeHtml(match.score || match.status)}</span></div>`).join('')}</div></article></section>`;
      target.querySelectorAll('[data-event-ref]').forEach((button) => button.addEventListener('click', () => openDraw(button.dataset.eventRef)));
    } catch (error) { target.innerHTML = `<section class="panel empty-panel"><h2>Round Centre unavailable</h2><p>${escapeHtml(error.message)}</p></section>`; }
  }

  async function renderHealth() {
    const target = $('#health-content');
    try {
      const health = await loadJson(data.modelHealthRef || 'model_health.json');
      const quality = health.quality || {};
      target.innerHTML = `<section class="audit-banner panel"><strong>${escapeHtml(health.label)}</strong><p>${escapeHtml(health.note)}</p></section><section class="stats-grid"><article><span>Eligible scorelines</span><strong>${fmt(health.eligibleMatches)}</strong></article><article><span>Match Brier score</span><strong>${fmt(health.brierScore)}</strong></article><article><span>Log loss</span><strong>${fmt(health.logLoss)}</strong></article><article><span>Mean game-share error</span><strong>${fmt(health.meanGameShareError)}</strong></article></section><section class="profile-grid"><article class="panel"><h2>Calibration</h2><div class="table-wrap"><table><thead><tr><th>Prediction bin</th><th>Matches</th><th>Predicted</th><th>Actual</th></tr></thead><tbody>${(health.calibration || []).map((item) => `<tr><td>${item.label}</td><td>${fmt(item.matches)}</td><td>${pct(item.meanPredicted)}</td><td>${pct(item.actualWinRate)}</td></tr>`).join('') || '<tr><td colspan="4">No diagnostic rows.</td></tr>'}</tbody></table></div></article><article class="panel"><h2>Import quality</h2><div class="quality-list"><div><span>Unique rows</span><strong>${fmt(quality.uniqueMatchRows)}</strong></div><div><span>Completed</span><strong>${fmt(quality.completed)}</strong></div><div><span>Retirements</span><strong>${fmt(quality.retirements)}</strong></div><div><span>Walkovers</span><strong>${fmt(quality.walkovers)}</strong></div><div><span>Scoreless completed</span><strong>${fmt(quality.scorelessCompleted)}</strong></div></div></article></section><section class="panel"><h2>Game-share error by surface</h2><div class="table-wrap"><table><thead><tr><th>Surface</th><th>Scorelines</th><th>Mean absolute error</th></tr></thead><tbody>${(health.surfaceDiagnostics || []).map((item) => `<tr><td>${escapeHtml(item.surface || 'Unknown')}</td><td>${fmt(item.matches)}</td><td>${fmt(item.meanGameShareError)}</td></tr>`).join('') || '<tr><td colspan="3">No diagnostic rows.</td></tr>'}</tbody></table></div></section>`;
    } catch (error) { target.innerHTML = `<section class="panel empty-panel"><h2>Diagnostics unavailable</h2><p>${escapeHtml(error.message)}</p></section>`; }
  }

  function populateEvents() {
    const events = data.tournaments || [];
    const selectOptions = events.map((event) => `<option value="${escapeHtml(event.detailRef)}">${escapeHtml(event.name)} · ${escapeHtml(event.startDate)}</option>`).join('');
    $('#draw-event-select').innerHTML = selectOptions;
    [...new Set(events.map((event) => event.type))].sort().forEach((type) => $('#event-type-filter').insertAdjacentHTML('beforeend', `<option value="${escapeHtml(type)}">${escapeHtml(type)}</option>`));
  }

  function exportRatings() {
    const heading = ['rank','player','power','wins','losses','matches','ci95_low','ci95_high'];
    const rows = (data.rankings || []).map((p) => [p.rank, p.player, p.rating, p.wins, p.losses, p.matches, p.lo, p.hi]);
    const csv = [heading, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n');
    const anchor = document.createElement('a'); anchor.href = URL.createObjectURL(new Blob([csv], {type:'text/csv'})); anchor.download = 'atp-power-ratings.csv'; anchor.click(); URL.revokeObjectURL(anchor.href);
  }

  document.querySelectorAll('[data-view]').forEach((link) => link.addEventListener('click', (event) => { event.preventDefault(); setView(link.dataset.view); }));
  window.addEventListener('hashchange', () => setView(location.hash.slice(1) || 'today'));
  $('#theme-toggle').addEventListener('click', () => { document.body.classList.toggle('high-contrast'); localStorage.setItem('atp-theme', document.body.classList.contains('high-contrast') ? 'high-contrast' : 'default'); });
  if (localStorage.getItem('atp-theme') === 'high-contrast') document.body.classList.add('high-contrast');
  $('#ranking-search').addEventListener('input', renderRankings); $('#show-provisional').addEventListener('change', renderRankings);
  $('#open-selected-player').addEventListener('click', () => openPlayer($('#player-select').value));
  $('#run-matchup').addEventListener('click', renderMatchup); $('#load-draw').addEventListener('click', () => openDraw($('#draw-event-select').value));
  $('#event-search').addEventListener('input', renderTournaments); $('#event-type-filter').addEventListener('change', renderTournaments);
  $('#result-search').addEventListener('input', renderResults); $('#result-status').addEventListener('change', renderResults); $('#export-ratings').addEventListener('click', exportRatings);
  hydrateStatus(); populatePlayers(); populateEvents(); renderRankings(); renderTournaments(); renderResults(); setView(location.hash.slice(1) || 'today');
})();
