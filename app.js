(() => {
  const data = window.ATP_RATINGS_DATA || {};
  const $ = (selector) => document.querySelector(selector);

  function setView(name) {
    const safeName = document.querySelector(`[data-panel="${name}"]`) ? name : 'rankings';
    document.querySelectorAll('[data-panel]').forEach((panel) => panel.classList.toggle('is-visible', panel.dataset.panel === safeName));
    document.querySelectorAll('[data-view]').forEach((link) => link.classList.toggle('active', link.dataset.view === safeName));
    if (window.location.hash !== `#${safeName}`) history.replaceState(null, '', `#${safeName}`);
  }

  function hydrateStatus() {
    const meta = data.meta || {};
    $('[data-stat="players"]').textContent = meta.players?.toLocaleString() || '—';
    $('[data-stat="matches"]').textContent = meta.matches?.toLocaleString() || '—';
    $('[data-stat="event"]').textContent = meta.latestEvent || '—';
    $('[data-stat="updated"]').textContent = meta.updatedAt ? new Date(meta.updatedAt).toLocaleString() : 'Not connected';
  }

  function cell(value) {
    const td = document.createElement('td');
    td.textContent = value;
    return td;
  }

  function renderTable(id, rows, makeRow, columns) {
    const target = $(`#${id}`);
    if (!target) return;
    target.replaceChildren();
    if (!rows.length) {
      const row = document.createElement('tr');
      const empty = cell('No published data yet.');
      empty.colSpan = columns;
      empty.className = 'loading-cell';
      row.append(empty);
      target.append(row);
      return;
    }
    rows.forEach((item) => target.append(makeRow(item)));
  }

  function renderData() {
    renderTable('rankings-table', data.rankings || [], (item) => {
      const row = document.createElement('tr');
      row.append(cell(item.rank), cell(item.player), cell(item.rating), cell(`${item.wins}–${item.losses}`), cell(item.matches), cell(`${item.lo}–${item.hi}`));
      return row;
    }, 6);
    renderTable('tournaments-table', (data.tournaments || []).slice(0, 200), (item) => {
      const row = document.createElement('tr');
      row.append(cell(item.name), cell(item.type), cell(`${item.surface}${item.indoor && item.indoor !== 'N' ? ' · indoor' : ''}`), cell(`${item.startDate} → ${item.endDate}`), cell(item.matches));
      return row;
    }, 5);
    renderTable('results-table', data.recentMatches || [], (item) => {
      const row = document.createElement('tr');
      row.append(cell(item.date), cell(item.event), cell(item.round), cell(item.winner), cell(item.score), cell(item.loser));
      return row;
    }, 6);
  }

  document.querySelectorAll('[data-view]').forEach((link) => link.addEventListener('click', (event) => {
    event.preventDefault();
    setView(link.dataset.view);
  }));
  window.addEventListener('hashchange', () => setView(location.hash.slice(1) || 'rankings'));
  $('#theme-toggle').addEventListener('click', () => {
    document.body.classList.toggle('high-contrast');
    localStorage.setItem('atp-theme', document.body.classList.contains('high-contrast') ? 'high-contrast' : 'default');
  });
  if (localStorage.getItem('atp-theme') === 'high-contrast') document.body.classList.add('high-contrast');
  hydrateStatus();
  renderData();
  setView(location.hash.slice(1) || 'rankings');
})();
