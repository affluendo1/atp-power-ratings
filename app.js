(() => {
  const data = window.ATP_RATINGS_DATA || {};
  const $ = (selector) => document.querySelector(selector);

  function setView(name) {
    document.querySelectorAll('[data-panel]').forEach((panel) => panel.classList.toggle('is-visible', panel.dataset.panel === name));
    document.querySelectorAll('[data-view]').forEach((link) => link.classList.toggle('active', link.dataset.view === name));
    if (window.location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);
  }

  function hydrateStatus() {
    const meta = data.meta || {};
    const players = data.players || [];
    const matches = data.matches || [];
    $('[data-stat="players"]').textContent = players.length || '—';
    $('[data-stat="matches"]').textContent = matches.length || '—';
    $('[data-stat="event"]').textContent = meta.latestEvent || '—';
    $('[data-stat="updated"]').textContent = meta.updatedAt || 'Not connected';
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
  setView(location.hash.slice(1) || 'rankings');
})();
