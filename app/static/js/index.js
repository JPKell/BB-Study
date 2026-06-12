/**
 * BB Study – Reading / index page logic.
 * Requires CURRENT_BOOK_ID and CURRENT_PAGE to be set by the template.
 */
const BB_STUDY_CONTEXT = window.BB_STUDY_CONTEXT || {};
const CURRENT_BOOK_ID = BB_STUDY_CONTEXT.currentBookId || null;
const CURRENT_PAGE = BB_STUDY_CONTEXT.currentPage || null;
const CONTENT_MODE = BB_STUDY_CONTEXT.contentMode || 'sentence';
const SECONDARY_BOOK_ID = BB_STUDY_CONTEXT.secondaryBookId || null;
const SECONDARY_PAGE = BB_STUDY_CONTEXT.secondaryPage || null;
const SECONDARY_CONTENT_MODE = BB_STUDY_CONTEXT.secondaryContentMode || 'sentence';
let currentRefEditId = null;
let currentCommEditId = null;
let currentReflectEditId = null;
let currentTopicLinkEditId = null;
let currentSourceEditId = null;
let topicPickingEnd = false;
let currentVerseSelection = null;
const TOPIC_DRAFT_KEY = 'bb-study-topic-draft';
const BOOK_PANE_TAB_KEY = 'bb-study-active-book-pane-tab';
const ACTIVE_TAB_KEY = 'bb-study-active-entry-tab';

/* ── Page navigation ───────────────────────────────────────────────────────── */

document.getElementById('pageInput')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') loadPage();
});
document.getElementById('pageInput')?.addEventListener('change', loadPage);
document.getElementById('bookSelect')?.addEventListener('change', function () {
  const bookId = this.value;
  if (bookId) {
    persistSetting('current_book_id', bookId).then(() => {
      window.location.href = buildReaderUrl({ bookId, page: null });
    });
  }
});
document.getElementById('primaryTocSelect')?.addEventListener('change', function () {
  if (!this.value) return;
  setValue('pageInput', this.value);
  loadPage();
});
document.getElementById('contentModeSelect')?.addEventListener('change', loadPage);
document.getElementById('secondaryBookSelect')?.addEventListener('change', function () {
  const bookId = this.value;
  if (!bookId) return;
  localStorage.setItem(BOOK_PANE_TAB_KEY, '#secondaryBookPane');
  persistSetting('current_secondary_book_id', bookId).then(() => {
    window.location.href = buildReaderUrl({ secondaryBookId: bookId, secondaryPage: null });
  });
});
document.getElementById('secondaryPageInput')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') loadSecondaryPage();
});
document.getElementById('secondaryPageInput')?.addEventListener('change', loadSecondaryPage);
document.getElementById('secondaryTocSelect')?.addEventListener('change', function () {
  if (!this.value) return;
  setValue('secondaryPageInput', this.value);
  loadSecondaryPage();
});
document.getElementById('secondaryContentModeSelect')?.addEventListener('change', loadSecondaryPage);
document.getElementById('readSearchQuery').addEventListener('keydown', e => {
  if (e.key === 'Enter') runReadSearch();
  if (e.key === 'Escape') hideReadSearchResults();
});
document.getElementById('readSearchQuery').addEventListener('input', e => {
  if (!e.target.value.trim()) hideReadSearchResults();
});
document.addEventListener('click', e => {
  if (!e.target.closest('#readSearchQuery') && !e.target.closest('#readSearchResults')) {
    hideReadSearchResults();
  }
});
document.getElementById('verseBoldBtn')?.addEventListener('click', () => toggleSelectedVerseFormat('bold'));
document.getElementById('verseItalicBtn')?.addEventListener('click', () => toggleSelectedVerseFormat('italic'));
document.getElementById('saveFormatBtn')?.addEventListener('click', () => saveSelectedVerseFormat());
document.getElementById('pageCenteredExportSwitch')?.addEventListener('change', savePageFormat);
document.getElementById('addSrcUrlBtn')?.addEventListener('click', () => addSourceUrlField());
document.getElementById('saveReflectBtn')?.addEventListener('click', saveReflectPrompt);

function loadPage() {
  const page = document.getElementById('pageInput').value.trim();
  if (!page) return;
  const bookId = document.getElementById('bookSelect')?.value || CURRENT_BOOK_ID;
  const modeSelect = document.getElementById('contentModeSelect');
  const mode = modeSelect ? modeSelect.value : (typeof CONTENT_MODE === 'undefined' ? 'sentence' : CONTENT_MODE);
  Promise.all([
    persistSetting('current_page', page),
    bookId ? persistSetting(`book_${bookId}_page`, page) : Promise.resolve(),
    bookId ? persistSetting(`book_${bookId}_content_mode`, mode) : Promise.resolve(),
  ]).then(() => {
    window.location.href = buildReaderUrl({ bookId, page, contentMode: mode });
  });
}

function loadSecondaryPage() {
  const bookId = document.getElementById('secondaryBookSelect')?.value || SECONDARY_BOOK_ID;
  if (!bookId) { showAlert('Select a second book first', 'warning'); return; }
  const page = document.getElementById('secondaryPageInput')?.value.trim();
  if (!page) return;
  const mode = document.getElementById('secondaryContentModeSelect')?.value || SECONDARY_CONTENT_MODE || 'sentence';
  Promise.all([
    persistSetting('current_secondary_book_id', bookId),
    persistSetting(`book_${bookId}_page`, page),
    persistSetting(`book_${bookId}_content_mode`, mode),
  ]).then(() => {
    localStorage.setItem(BOOK_PANE_TAB_KEY, '#secondaryBookPane');
    window.location.href = buildReaderUrl({ secondaryBookId: bookId, secondaryPage: page, secondaryContentMode: mode });
  });
}

function buildReaderUrl(overrides = {}) {
  const primaryBookId = overrides.bookId !== undefined
    ? overrides.bookId
    : (document.getElementById('bookSelect')?.value || CURRENT_BOOK_ID || '');
  const primaryPage = overrides.page !== undefined
    ? overrides.page
    : (document.getElementById('pageInput')?.value.trim() || CURRENT_PAGE || '');
  const primaryMode = overrides.contentMode !== undefined
    ? overrides.contentMode
    : (document.getElementById('contentModeSelect')?.value || CONTENT_MODE || 'sentence');

  const secondaryBookId = overrides.secondaryBookId !== undefined
    ? overrides.secondaryBookId
    : (document.getElementById('secondaryBookSelect')?.value || SECONDARY_BOOK_ID || '');
  const secondaryPage = overrides.secondaryPage !== undefined
    ? overrides.secondaryPage
    : (document.getElementById('secondaryPageInput')?.value.trim() || SECONDARY_PAGE || '');
  const secondaryMode = overrides.secondaryContentMode !== undefined
    ? overrides.secondaryContentMode
    : (document.getElementById('secondaryContentModeSelect')?.value || SECONDARY_CONTENT_MODE || 'sentence');

  const params = new URLSearchParams();
  if (primaryBookId) params.set('book_id', primaryBookId);
  if (primaryBookId && primaryPage) params.set('page', primaryPage);
  if (primaryBookId && primaryMode) params.set('content_mode', primaryMode);
  if (secondaryBookId) params.set('secondary_book_id', secondaryBookId);
  if (secondaryBookId && secondaryPage) params.set('secondary_page', secondaryPage);
  if (secondaryBookId && secondaryMode) params.set('secondary_content_mode', secondaryMode);
  const query = params.toString();
  return query ? `/?${query}` : '/';
}

function persistSetting(key, value) {
  return fetch(`/api/settings/${key}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: String(value) }),
  });
}

async function loadPageFormat() {
  const control = document.getElementById('pageCenteredExportSwitch');
  if (!control || !CURRENT_BOOK_ID || !CURRENT_PAGE) return;
  const params = new URLSearchParams({ book_id: CURRENT_BOOK_ID, page: CURRENT_PAGE });
  const response = await fetch(`/api/book-page-format?${params.toString()}`);
  if (!response.ok) return;
  const data = await response.json();
  control.checked = !!data.centered_export;
}

async function savePageFormat() {
  const control = document.getElementById('pageCenteredExportSwitch');
  if (!control || !CURRENT_BOOK_ID || !CURRENT_PAGE) return;
  control.disabled = true;
  const response = await fetch('/api/book-page-format', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      book_id: CURRENT_BOOK_ID,
      page: CURRENT_PAGE,
      centered_export: control.checked,
    }),
  });
  control.disabled = false;
  if (!response.ok) {
    showAlert('Could not save page format', 'danger');
    return;
  }
  showAlert('Page format saved', 'success', 1200);
}

/* ── Read search dropdown ──────────────────────────────────────────────────── */

function runReadSearch() {
  const input = document.getElementById('readSearchQuery');
  const results = document.getElementById('readSearchResults');
  const q = input.value.trim();
  if (!q) return;
  const params = new URLSearchParams({ q });
  if (CURRENT_BOOK_ID) params.set('book_id', CURRENT_BOOK_ID);
  results.classList.remove('d-none');
  results.innerHTML = '<div class="search-result-item text-muted">Searching...</div>';
  fetch(`/api/search?${params.toString()}`)
    .then(r => r.json())
    .then(data => {
      if (!data.length) {
        results.innerHTML = '<div class="search-result-item text-muted">No results found.</div>';
        return;
      }
      results.innerHTML = data.map(renderSearchResult).join('');
    });
}

function hideReadSearchResults() {
  const results = document.getElementById('readSearchResults');
  if (results) results.classList.add('d-none');
}

function renderSearchResult(result) {
  const query = document.getElementById('readSearchQuery')?.value.trim() || '';
  if (result.result_type === 'pamphlet') {
    return `<button class="search-result-item text-start w-100 border-0" type="button"
              onclick="openPamphletPanel(${result.pamphlet_id}); hideReadSearchResults();">
      <div class="d-flex justify-content-between gap-2">
        <strong>${escHtml(result.series || '')} ${escHtml(result.pamphlet_title || '')}</strong>
        <span class="text-muted small">pamphlet</span>
      </div>
      <div class="search-result-excerpt topic-snippet">${escHtml(makeTextSnippet(result.excerpt || '', query))}</div>
    </button>`;
  }
  const modeSelect = document.getElementById('contentModeSelect');
  const mode = modeSelect ? modeSelect.value : 'sentence';
  const href = `/?book_id=${result.book_id}&page=${encodeURIComponent(result.page || '')}&content_mode=${encodeURIComponent(mode)}`;
  const location = `${escHtml(result.chapter_name || '')} · p. ${escHtml(result.page || '')} · ¶${result.paragraph || ''} · v${result.verse || ''}`;
  const topics = (result.topics || []).map(topic => `<span class="badge text-bg-secondary me-1">${escHtml(topic.name)}</span>`).join('');
  return `<a class="search-result-item" href="${href}">
    <div class="d-flex justify-content-between gap-2">
      <strong>${location}</strong>
      <span class="text-muted small">${escHtml(result.match_type || '')}</span>
    </div>
    <div class="search-result-excerpt topic-snippet">${escHtml(makeTextSnippet(result.excerpt || '', query))}</div>
    <div>${topics}</div>
  </a>`;
}

/* ── Pamphlet side reader ──────────────────────────────────────────────────── */

document.getElementById('pamphletPanelToggle')?.addEventListener('click', () => openPamphletPanel());
document.getElementById('pamphletSearchBtn')?.addEventListener('click', searchPamphlets);
document.getElementById('pamphletSearchQuery')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') searchPamphlets();
});
document.getElementById('pamphletSearchQuery')?.addEventListener('input', e => {
  if (!e.target.value.trim()) {
    document.getElementById('pamphletSearchResults').innerHTML = '';
  }
});
document.getElementById('pamphletSelect')?.addEventListener('change', e => {
  const pamphletId = parseInt(e.target.value, 10);
  if (pamphletId) loadPamphlet(pamphletId);
});

function loadPamphletOptions() {
  const select = document.getElementById('pamphletSelect');
  if (!select) return;

  fetch('/api/pamphlets')
    .then(r => r.json())
    .then(pamphlets => {
      if (!pamphlets.length) {
        select.innerHTML = '<option value="">No pamphlets available</option>';
        return;
      }
      select.innerHTML = '<option value="">Choose a pamphlet...</option>' + pamphlets.map(p => {
        const label = `${p.series || ''} ${p.title || ''}`.trim() || 'Untitled pamphlet';
        return `<option value="${p.id}">${escHtml(label)}</option>`;
      }).join('');
      if (select.dataset.currentPamphletId) {
        select.value = select.dataset.currentPamphletId;
      }
    })
    .catch(() => {
      select.innerHTML = '<option value="">Could not load pamphlets</option>';
    });
}

function openPamphletPanel(pamphletId) {
  showBookPaneTab('#pamphletBookPane');
  if (!pamphletId) document.querySelector('.pamphlet-reader-search')?.classList.remove('d-none');
  if (pamphletId) loadPamphlet(pamphletId);
}

function showBookPaneTab(target) {
  const trigger = document.querySelector(`#bookPaneTabs [data-bs-target="${target}"]`);
  if (!trigger) return;
  localStorage.setItem(BOOK_PANE_TAB_KEY, target);
  bootstrap.Tab.getOrCreateInstance(trigger).show();
}

function searchPamphlets() {
  const q = document.getElementById('pamphletSearchQuery').value.trim();
  const results = document.getElementById('pamphletSearchResults');
  if (!q) return;
  results.innerHTML = '<button class="pamphlet-result text-muted" type="button">Searching...</button>';
  fetch(`/api/pamphlets/search?q=${encodeURIComponent(q)}`)
    .then(r => r.json())
    .then(data => {
      if (!data.length) {
        results.innerHTML = '<button class="pamphlet-result text-muted" type="button">No pamphlets found.</button>';
        return;
      }
      results.innerHTML = data.map(p => `<button class="pamphlet-result" type="button" onclick="loadPamphlet(${p.id})">
        <span class="fw-semibold">${escHtml(p.series || '')}</span> ${escHtml(p.title || '')}
        <span class="d-block text-muted topic-snippet">${escHtml(makeTextSnippet(p.excerpt || '', q))}</span>
      </button>`).join('');
    });
}

function loadPamphlet(pamphletId) {
  const status = document.getElementById('pamphletPanelStatus');
  const empty = document.getElementById('pamphletEmptyState');
  const view = document.getElementById('pamphletContentView');
  const select = document.getElementById('pamphletSelect');
  if (status) status.textContent = 'Loading...';
  if (empty) empty.classList.add('d-none');
  if (select) {
    select.dataset.currentPamphletId = String(pamphletId);
    select.value = String(pamphletId);
  }
  if (view) view.innerHTML = '<p class="text-muted small">Loading pamphlet text...</p>';

  Promise.all([
    fetch(`/api/pamphlets/${pamphletId}`).then(r => r.json()),
    fetch(`/api/pamphlets/${pamphletId}/content`).then(r => r.json()),
  ]).then(([pamphlet, rows]) => {
    if (status) status.textContent = `${pamphlet.series || ''} ${pamphlet.title || ''}`.trim();
    const grouped = new Map();
    rows.forEach(row => {
      const page = row.page || '';
      if (!grouped.has(page)) grouped.set(page, []);
      grouped.get(page).push(row);
    });
    view.innerHTML = `<div class="mb-3">
      <h6 class="mb-1">${escHtml(pamphlet.title || '')}</h6>
      <div class="text-muted small">${escHtml(pamphlet.series || '')} · ${escHtml(pamphlet.publisher || '')}</div>
    </div>${[...grouped.entries()].map(([page, pageRows]) => `
      <section class="pamphlet-page">
        <div class="pamphlet-page-label">Page ${escHtml(page || '—')}</div>
        ${pageRows.map(row => `<p><span class="pamphlet-fragment" data-pamphlet-content-id="${row.id}" data-raw-content="${escAttr(row.content || '')}">${escHtml(row.content || '')}</span></p>`).join('')}
      </section>`).join('')}`;
  }).catch(() => {
    if (status) status.textContent = 'Could not load pamphlet';
    if (view) view.innerHTML = '<p class="text-danger small">Failed to load pamphlet text.</p>';
  });
}

function openPamphletFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const pamphletId = parseInt(params.get('pamphlet_id'));
  if (pamphletId) openPamphletPanel(pamphletId);
}

/* ── Page summary loader ────────────────────────────────────────────────────── */

function loadPageSummary() {
  if (!CURRENT_BOOK_ID || !CURRENT_PAGE) return;
  const summaryEl = document.getElementById('pageSummary');
  if (!summaryEl) return;

  document.getElementById('summaryPageLabel').textContent = CURRENT_PAGE;

  fetch(`/api/page-summary?book_id=${CURRENT_BOOK_ID}&page=${encodeURIComponent(CURRENT_PAGE)}`)
    .then(r => r.json())
    .then(data => {
      summaryEl.innerHTML = '';
      const summaryCards = [];

      // Commentary
      if (data.commentary && data.commentary.length) {
        data.commentary.forEach(c => {
          const loc = makeLocationText([
            ['Ch', c.chapter],
            ['Page', c.page],
            ['Para', c.paragraph],
            ['Verse', c.verse || c.line],
          ]);
          summaryCards.push(makeSummaryCard('Commentary', 'commentary',
            `${rankBadge(c.rank)}
             <p class="mb-1">${escHtml(c.commentary_text)}</p>
             ${loc ? `<small class="text-muted">${escHtml(loc)}</small>` : ''}`,
            c.id, 'commentary', 'commentary', c.rank));
        });
      }

      // Book references
      if (data.references && data.references.length) {
        data.references.forEach(r => {
          summaryCards.push(makeSummaryCard('Book Reference', 'reference',
            `${rankBadge(r.rank)}
             <p class="mb-1 fst-italic">${escHtml(r.quoted_text || '')}</p>
             <p class="mb-0 small">→ <strong>${escHtml(r.target_book_title || '')}</strong>
               Ch: ${escHtml(r.target_chapter || '—')} · Pg: ${escHtml(r.target_page || '—')}</p>
             ${r.comments ? `<p class="text-muted small mb-0">${escHtml(r.comments)}</p>` : ''}`,
            r.id, 'references', 'reference', r.rank));
        });
      }

      // Other references / sources
      if (data.sources && data.sources.length) {
        data.sources.forEach(s => {
          const ref = renderSourceReferences(s.urls || (s.url ? [s.url] : []));
          const loc = s.page || s.paragraph || s.verse
            ? `<div class="text-muted small mb-1">p. ${escHtml(s.page || '')} · ¶${s.paragraph || ''} · v${s.verse || s.line || ''}</div>`
            : '';
          summaryCards.push(makeSummaryCard('Other Ref', 'reference',
            `${rankBadge(s.rank)}
             <div class="mb-1"><span class="badge text-bg-secondary">${escHtml(s.source_type || 'other')}</span></div>
             <p class="mb-1 fw-semibold">${escHtml(s.name || '')}</p>
             ${loc}
             ${ref}
             ${s.notes ? `<p class="text-muted small mb-0">${escHtml(s.notes)}</p>` : ''}`,
            s.id, 'sources', 'source', s.rank));
        });
      }

      // Dictionary lookups
      if (data.dictionary && data.dictionary.length) {
        summaryCards.push(makeDictionarySummaryCard(data.dictionary));
      }

      // Reflect prompts
      if (data.reflect && data.reflect.length) {
        data.reflect.forEach(prompt => {
          const loc = makeLocationText([
            ['Ch', prompt.chapter],
            ['Page', prompt.page],
            ['Para', prompt.paragraph],
            ['Verse', prompt.verse || prompt.line],
          ]);
          summaryCards.push(makeSummaryCard('Reflect', 'commentary',
            `${rankBadge(prompt.rank)}
             <p class="mb-1">${escHtml(prompt.prompt_text)}</p>
             ${loc ? `<small class="text-muted">${escHtml(loc)}</small>` : ''}`,
            prompt.id, 'reflect-prompts', 'reflect', prompt.rank));
          summaryCards[summaryCards.length - 1].dataset.sectionOrder = '20';
        });
      }

      // Topic tags linked to content on this page
      if (data.topics && data.topics.length) {
        data.topics.forEach(link => {
          const loc = `p. ${escHtml(link.page || '')} · ¶${link.paragraph || ''} · v${link.verse || ''}`;
          summaryCards.push(makeSummaryCard('Tag', 'reference',
            `${rankBadge(link.rank)}
             <div class="mb-1"><span class="badge text-bg-secondary">${escHtml(link.topic_name || '')}</span></div>
             <p class="mb-1 small text-muted">${loc}</p>
             <p class="mb-1 topic-snippet">${escHtml(makeTextSnippet(link.content || ''))}</p>
             ${link.notes ? `<p class="text-muted small mb-0">${escHtml(link.notes)}</p>` : ''}`,
            link.id, 'content-topics', 'topic-link', link.rank));
        });
      }

      if (!summaryCards.length) {
        summaryEl.innerHTML = '<p class="text-muted small mb-0">No annotations for this page yet.</p>';
        return;
      }
      assignFallbackRanks(summaryCards);
      renderBalancedSummaryCards(summaryEl, summaryCards);
    })
    .catch(() => {
      const summaryEl = document.getElementById('pageSummary');
      if (summaryEl) summaryEl.innerHTML = '<p class="text-danger small mb-0">Failed to load page summary.</p>';
    });
}

function makeSummaryCard(label, typeClass, bodyHtml, id, endpoint, annotationType, rank) {
  const card = document.createElement('div');
  card.className = `card summary-card ${typeClass} annotation-card`;
  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');
  card.dataset.annotationType = annotationType;
  card.dataset.id = id;
  card.dataset.rank = rank || '';
  card.innerHTML = `
      <div class="card-header d-flex justify-content-between align-items-center py-1 px-2">
        <small class="fw-semibold text-uppercase">${label}</small>
        <div class="btn-group btn-group-sm" role="group" aria-label="Rank and delete">
          ${rankMoveButtons(endpoint, id, rank)}
          <button class="btn btn-sm btn-outline-danger border-0 py-0"
                  onclick="event.stopPropagation(); deleteSummaryItem('${endpoint}', ${id})" title="Delete">
            <i class="bi bi-trash"></i>
          </button>
        </div>
      </div>
      <div class="card-body py-2 px-2 small">${bodyHtml}</div>`;
  return card;
}

function rankBadge(rank) {
  return rank ? `<div class="mb-1"><span class="badge text-bg-light text-secondary">Rank ${escHtml(rank)}</span></div>` : '';
}

function rankMoveButtons(endpoint, id, rank) {
  const rankValue = rank || '';
  return `
    <button class="btn btn-sm btn-outline-secondary border-0 py-0 rank-move-btn" type="button"
            data-endpoint="${endpoint}" data-id="${id}" data-rank="${rankValue}" data-direction="-1" title="Move up">
      <i class="bi bi-arrow-up"></i>
    </button>
    <button class="btn btn-sm btn-outline-secondary border-0 py-0 rank-move-btn" type="button"
            data-endpoint="${endpoint}" data-id="${id}" data-rank="${rankValue}" data-direction="1" title="Move down">
      <i class="bi bi-arrow-down"></i>
    </button>`;
}

function makeDictionarySummaryCard(entries) {
  const card = document.createElement('div');
  card.className = 'card summary-card dictionary';
  const rows = entries.map(entry => `
    <div class="dictionary-summary-row d-flex align-items-start gap-2">
      <button class="dictionary-summary-entry text-start flex-grow-1" type="button"
              data-annotation-type="dictionary" data-id="${entry.id}">
        ${entry.rank ? `<span class="badge text-bg-light text-secondary me-1">Rank ${escHtml(entry.rank)}</span>` : ''}
        <span class="fw-semibold">${escHtml(entry.word_phrase || '')}</span>
        <span class="text-muted"> — ${escHtml(makeTextSnippet(entry.meaning || '', ''))}</span>
      </button>
      <div class="btn-group btn-group-sm" role="group" aria-label="Rank and delete">
        ${rankMoveButtons('dictionary-lookup', entry.id, entry.rank)}
        <button class="btn btn-sm btn-outline-danger border-0 py-0 dictionary-summary-delete"
                type="button" data-id="${entry.id}" title="Delete">
          <i class="bi bi-trash"></i>
        </button>
      </div>
    </div>`).join('');
  card.innerHTML = `
      <div class="card-header py-1 px-2">
        <small class="fw-semibold text-uppercase">Dictionary</small>
      </div>
      <div class="card-body py-2 px-2 small dictionary-summary-list">${rows}</div>`;
  card.dataset.sectionOrder = '10';
  return card;
}

function renderBalancedSummaryCards(summaryEl, cards) {
  summaryEl.innerHTML = '';
  const columnCount = getSummaryColumnCount(summaryEl);
  const columns = Array.from({ length: columnCount }, () => {
    const column = document.createElement('div');
    column.className = 'summary-column';
    summaryEl.appendChild(column);
    return column;
  });

  const anchoredCards = cards
    .filter(card => summaryCardSectionOrder(card) < 100)
    .sort((a, b) => summaryCardSectionOrder(a) - summaryCardSectionOrder(b) || summaryCardRank(a) - summaryCardRank(b));
  anchoredCards.forEach(card => columns[0].appendChild(card));

  const balancedCards = cards
    .filter(card => summaryCardSectionOrder(card) >= 100)
    .sort((a, b) => summaryCardRank(a) - summaryCardRank(b));
  measureSummaryCards(balancedCards, columns[0]).forEach(({ card }) => {
    const shortestColumn = columns.reduce((shortest, column) =>
      column.scrollHeight < shortest.scrollHeight ? column : shortest);
    shortestColumn.appendChild(card);
  });
}

function assignFallbackRanks(cards) {
  const buttons = cards.flatMap(card => [...card.querySelectorAll('.rank-move-btn')]);
  let maxRank = buttons
    .map(btn => parseInt(btn.dataset.rank))
    .filter(Boolean)
    .reduce((max, rank) => Math.max(max, rank), 0);
  buttons.forEach(btn => {
    if (parseInt(btn.dataset.rank)) return;
    maxRank += 1;
    btn.dataset.rank = String(maxRank);
  });
  cards.forEach(card => {
    if (parseInt(card.dataset.rank)) return;
    const rank = [...card.querySelectorAll('.rank-move-btn')]
      .map(btn => parseInt(btn.dataset.rank))
      .filter(Boolean)
      .sort((a, b) => a - b)[0];
    if (rank) card.dataset.rank = String(rank);
  });
}

function summaryCardRank(card) {
  const rank = parseInt(card.dataset.rank);
  if (rank) return rank;
  const rowRank = [...card.querySelectorAll('.rank-move-btn')]
    .map(btn => parseInt(btn.dataset.rank))
    .filter(Boolean)
    .sort((a, b) => a - b)[0];
  return rowRank || Number.MAX_SAFE_INTEGER;
}

function summaryCardSectionOrder(card) {
  return parseInt(card.dataset.sectionOrder) || 100;
}

function measureSummaryCards(cards, sampleColumn) {
  const measureColumn = document.createElement('div');
  measureColumn.className = 'summary-column summary-measure-column';
  measureColumn.style.width = `${sampleColumn.getBoundingClientRect().width}px`;
  document.body.appendChild(measureColumn);

  const measured = cards.map(card => {
    measureColumn.appendChild(card);
    const height = card.getBoundingClientRect().height;
    measureColumn.removeChild(card);
    return { card, height };
  });

  measureColumn.remove();
  return measured;
}

function getSummaryColumnCount(summaryEl) {
  const columns = getComputedStyle(summaryEl).gridTemplateColumns
    .split(' ')
    .filter(Boolean);
  return Math.max(1, columns.length || 1);
}

document.addEventListener('click', e => {
  const rankMove = e.target.closest('.rank-move-btn');
  if (rankMove) {
    e.preventDefault();
    e.stopPropagation();
    moveSummaryRank(rankMove);
    return;
  }
  const dictionaryDelete = e.target.closest('.dictionary-summary-delete');
  if (dictionaryDelete) {
    deleteSummaryItem('dictionary-lookup', dictionaryDelete.dataset.id);
    return;
  }
  const dictionaryEntry = e.target.closest('.dictionary-summary-entry');
  if (dictionaryEntry) {
    loadAnnotationIntoEditor(dictionaryEntry.dataset.annotationType, dictionaryEntry.dataset.id);
    return;
  }
  const card = e.target.closest('.annotation-card');
  if (!card) return;
  loadAnnotationIntoEditor(card.dataset.annotationType, card.dataset.id);
});

async function moveSummaryRank(button) {
  const currentRank = parseInt(button.dataset.rank);
  const direction = parseInt(button.dataset.direction);
  if (!currentRank || !direction) {
    showAlert('Save this item once before moving its rank', 'warning');
    return;
  }
  const nextRank = currentRank + direction;
  if (nextRank < 1) return;
  button.disabled = true;
  const res = await fetch(`/api/${button.dataset.endpoint}/${button.dataset.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rank: nextRank }),
  }).then(r => r.json()).catch(() => ({ error: 'Rank update failed' }));
  if (res.error) {
    showAlert(res.error || 'Rank update failed', 'danger');
    button.disabled = false;
    return;
  }
  loadPageSummary();
}

function deleteSummaryItem(endpoint, id) {
  if (!confirm('Delete this item?')) return;
  fetch(`/api/${endpoint}/${id}`, { method: 'DELETE' })
    .then(() => loadPageSummary());
}

async function loadAnnotationIntoEditor(type, id) {
  if (type === 'commentary') {
    const data = await fetch(`/api/commentary/${id}`).then(r => r.json());
    currentCommEditId = data.id;
    setValue('commId', data.id);
    setValue('commChapter', data.chapter || '');
    setValue('commPage', data.page || CURRENT_PAGE || '');
    setValue('commPara', data.paragraph || '');
    setValue('commLine', data.verse || data.line || '');
    setValue('commText', data.commentary_text || '');
    setValue('commRank', data.rank || '');
    showTab('#tabComm');
  } else if (type === 'reflect') {
    const data = await fetch(`/api/reflect-prompts/${id}`).then(r => r.json());
    currentReflectEditId = data.id;
    setValue('reflectId', data.id);
    setValue('reflectChapter', data.chapter || '');
    setValue('reflectPage', data.page || CURRENT_PAGE || '');
    setValue('reflectPara', data.paragraph || '');
    setValue('reflectLine', data.verse || data.line || '');
    setValue('reflectText', data.prompt_text || '');
    setValue('reflectRank', data.rank || '');
    showTab('#tabReflect');
  } else if (type === 'reference') {
    const data = await fetch(`/api/references/${id}`).then(r => r.json());
    currentRefEditId = data.id;
    setValue('refId', data.id);
    setValue('refSrcChapter', data.source_chapter || '');
    setValue('refSrcPage', data.source_page || CURRENT_PAGE || '');
    setValue('refSrcPara', data.source_paragraph || '');
    setValue('refSrcLine', data.source_verse || data.source_line || '');
    setValue('refTargetBook', data.target_book_id || '');
    setValue('refTgtChapter', data.target_chapter || '');
    setValue('refTgtPage', data.target_page || '');
    setValue('refTgtPara', data.target_paragraph || '');
    setValue('refTgtLine', data.target_verse || data.target_line || '');
    setValue('refQuoted', data.quoted_text || '');
    setValue('refComments', data.comments || '');
    setValue('refRank', data.rank || '');
    showTab('#tabRef');
  } else if (type === 'dictionary') {
    const lookup = await fetch(`/api/dictionary-lookup/${id}`).then(r => r.json());
    setValue('dictLookupId', lookup.id);
    setValue('dictEntryId', lookup.dictionary_id || '');
    setValue('dictLocationId', lookup.book_location_id || '');
    setValue('dictWord', lookup.word_phrase || '');
    setValue('dictMeaning', lookup.meaning || '');
    setValue('dictNotes', lookup.notes || '');
    setValue('dictChapter', lookup.chapter || '');
    setValue('dictPage', lookup.page || CURRENT_PAGE || '');
    setValue('dictPara', lookup.paragraph || '');
    setValue('dictLine', lookup.line_number || '');
    setValue('dictLineText', lookup.line_text || '');
    setValue('dictRank', lookup.rank || '');
    showTab('#tabDict');
  } else if (type === 'topic-link') {
    const link = await fetch(`/api/content-topics/${id}`).then(r => r.json());
    currentTopicLinkEditId = link.id;
    setValue('topicLinkId', link.id);
    setValue('topicSelect', link.topic_id || '');
    setValue('topicNewName', '');
    setValue('topicNotes', link.notes || '');
    setValue('topicChapter', link.chapter_name || '');
    setValue('topicPage', link.page || CURRENT_PAGE || '');
    setValue('topicPara', link.paragraph || '');
    setValue('topicVerse', link.verse || '');
    setValue('topicSelectedText', makeTextSnippet(link.content || ''));
    setValue('topicContentIds', link.low_content_id && link.high_content_id ? `${link.low_content_id},${link.high_content_id}` : '');
    setValue('topicStartContentId', link.start_content_id || link.book_content_id || '');
    setValue('topicEndContentId', link.end_content_id || link.start_content_id || link.book_content_id || '');
    setValue('topicRank', link.rank || '');
    setTopicEditMode(true);
    saveTopicDraft();
    highlightTopicRange();
    showTab('#tabTopic');
  } else if (type === 'source') {
    const source = await fetch(`/api/sources/${id}`).then(r => r.json());
    currentSourceEditId = source.id;
    setValue('srcId', source.id);
    setValue('srcName', source.name || '');
    setValue('srcType', source.source_type || 'other');
    setValue('srcChapter', source.chapter || '');
    setValue('srcPage', source.page || CURRENT_PAGE || '');
    setValue('srcPara', source.paragraph || '');
    setValue('srcVerse', source.verse || source.line || '');
    setValue('srcAuthor', source.author || '');
    setSourceUrlFields(source.urls || (source.url ? [source.url] : ['']));
    setValue('srcNotes', source.notes || '');
    setValue('srcRank', source.rank || '');
    showTab('#tabSrc');
  }
}

function showTab(target) {
  const trigger = document.querySelector(`[data-bs-target="${target}"]`);
  if (trigger) {
    localStorage.setItem(ACTIVE_TAB_KEY, target);
    bootstrap.Tab.getOrCreateInstance(trigger).show();
  }
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(str) {
  return escHtml(str).replace(/'/g, '&#39;');
}

function makeTextSnippet(value, query = '') {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  const maxLength = 320;
  if (text.length <= maxLength) return text;

  const needle = String(query || '').replace(/\s+/g, ' ').trim().toLowerCase();
  if (needle) {
    const index = text.toLowerCase().indexOf(needle);
    if (index !== -1) {
      const start = Math.max(0, index - 120);
      const end = Math.min(text.length, index + needle.length + 180);
      return formatSnippetSlice(text, start, end);
    }
  }

  return `${trimSnippetText(text.slice(0, 220), false, true)} ... ${trimSnippetText(text.slice(-90), true, false)}`;
}

function formatSnippetSlice(text, start, end, trimStart = start > 0, trimEnd = end < text.length) {
  const snippet = trimSnippetText(text.slice(start, end), trimStart, trimEnd);
  return `${start > 0 ? '... ' : ''}${snippet}${end < text.length ? ' ...' : ''}`;
}

function trimSnippetText(value, trimStart, trimEnd) {
  let snippet = String(value || '').trim();
  if (trimStart) {
    const trimmed = snippet.replace(/^\S+\s+/, '');
    if (trimmed) snippet = trimmed;
  }
  if (trimEnd) {
    const trimmed = snippet.replace(/\s+\S+$/, '');
    if (trimmed) snippet = trimmed;
  }
  return snippet;
}

function makeLocationText(parts) {
  return parts
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([label, value]) => `${label}: ${value}`)
    .join(' · ');
}

/* ── Verse selection from page text ────────────────────────────────────────── */

document.addEventListener('click', e => {
  const fragment = e.target.closest('.verse-fragment');
  if (fragment && fragment.classList.contains('editing-fragment')) return;
  if (!fragment) return;
  if (topicPickingEnd) {
    selectTopicRangeEnd(fragment);
    return;
  }
  selectVerse(fragment);
});

document.addEventListener('dblclick', e => {
  const fragment = e.target.closest('.verse-fragment, .secondary-book-fragment, .pamphlet-fragment');
  if (!fragment) return;
  e.preventDefault();
  e.stopPropagation();
  editFragment(fragment);
});

function selectVerse(fragment) {
  const selection = getVerseSelection(fragment);
  currentVerseSelection = selection;
  const matches = selection.matches;
  document.querySelectorAll('.verse-fragment.selected-verse').forEach(el => {
    el.classList.remove('selected-verse');
  });
  matches.forEach(el => el.classList.add('selected-verse'));

  setValue('dictChapter', selection.chapter);
  setValue('dictPage', selection.page);
  setValue('dictPara', selection.paragraph);
  setValue('dictLine', selection.verse);
  setValue('dictLineText', selection.fullText);
  clearDictionaryEditState({ preservePage: true });
  setValue('refSrcChapter', selection.chapter);
  setValue('refSrcPage', selection.page);
  setValue('refSrcPara', selection.paragraph);
  setValue('refSrcLine', selection.verse);
  setValue('refQuoted', selection.fullText);
  setValue('commChapter', selection.chapter);
  setValue('commPage', selection.page);
  setValue('commPara', selection.paragraph);
  setValue('commLine', selection.verse);
  setValue('reflectChapter', selection.chapter);
  setValue('reflectPage', selection.page);
  setValue('reflectPara', selection.paragraph);
  setValue('reflectLine', selection.verse);
  setValue('srcChapter', selection.chapter);
  setValue('srcPage', selection.page);
  setValue('srcPara', selection.paragraph);
  setValue('srcVerse', selection.verse);
  setValue('topicChapter', selection.chapter);
  setValue('topicPage', selection.page);
  setValue('topicPara', selection.paragraph);
  setValue('topicVerse', selection.verse);
  setValue('topicSelectedText', makeTextSnippet(selection.fullText));
  setValue('topicContentIds', selection.ids.join(','));
  setValue('topicStartContentId', selection.lowId || '');
  setValue('topicEndContentId', selection.highId || '');
  setValue('formatSelectedText', selection.fullText);
  setValue('formatContentRole', selection.contentRole || 'body');
  setValue('splitContentId', selection.selectedId || '');
  setValue('splitOriginalText', selection.selectedText || '');
  setValue('splitMarkerText', selection.selectedText || '');
  resetTopicEditor();
  saveTopicDraft();
  updateVerseFormatButtons(selection);
}

function getVerseSelection(fragment) {
  const key = fragment.dataset.verseKey;
  const matches = [...document.querySelectorAll(`.verse-fragment[data-verse-key="${CSS.escape(key)}"]`)];
  const ids = matches.map(el => parseInt(el.dataset.contentId)).filter(Boolean);
  const parts = matches.map(el => (el.dataset.rawContent || el.textContent || '').trim());
  return {
    matches,
    ids,
    lowId: ids.length ? Math.min(...ids) : null,
    highId: ids.length ? Math.max(...ids) : null,
    fullText: combineVerseText(parts),
    chapter: fragment.dataset.chapter || '',
    page: fragment.dataset.page || CURRENT_PAGE || '',
    paragraph: fragment.dataset.paragraph || '',
    verse: fragment.dataset.verse || '',
    selectedId: parseInt(fragment.dataset.contentId) || null,
    selectedText: (fragment.dataset.rawContent || fragment.textContent || '').trim(),
    isBold: matches.some(el => el.dataset.isBold === 'true' || el.classList.contains('formatted-bold')),
    isItalic: matches.some(el => el.dataset.isItalic === 'true' || el.classList.contains('formatted-italic')),
    contentRole: matches.find(el => el.dataset.contentRole)?.dataset.contentRole || 'body',
    alignmentOverride: matches.find(el => el.dataset.alignmentOverride)?.dataset.alignmentOverride || '',
  };
}

function updateVerseFormatButtons(selection = currentVerseSelection) {
  const boldBtn = document.getElementById('verseBoldBtn');
  const italicBtn = document.getElementById('verseItalicBtn');
  if (!boldBtn || !italicBtn) return;
  const hasSelection = !!selection;
  boldBtn.disabled = !hasSelection;
  italicBtn.disabled = !hasSelection;
  boldBtn.classList.toggle('active', !!selection?.isBold);
  italicBtn.classList.toggle('active', !!selection?.isItalic);
  setValue('formatContentRole', selection?.contentRole || 'body');
  setValue('formatAlignmentOverride', selection?.alignmentOverride || '');
  setValue('formatSelectedText', selection?.fullText || '');
}

async function toggleSelectedVerseFormat(kind) {
  if (!currentVerseSelection || !CURRENT_BOOK_ID) {
    showAlert('Select a verse first', 'warning');
    return;
  }
  const nextBold = kind === 'bold' ? !currentVerseSelection.isBold : currentVerseSelection.isBold;
  const nextItalic = kind === 'italic' ? !currentVerseSelection.isItalic : currentVerseSelection.isItalic;
  await saveSelectedVerseFormat(
    nextBold,
    nextItalic,
    currentVerseSelection.contentRole || 'body',
    currentVerseSelection.alignmentOverride || ''
  );
}

async function saveSelectedVerseFormat(
  isBold = currentVerseSelection?.isBold,
  isItalic = currentVerseSelection?.isItalic,
  contentRole = document.getElementById('formatContentRole')?.value || 'body',
  alignmentOverride = document.getElementById('formatAlignmentOverride')?.value || ''
) {
  if (!currentVerseSelection || !CURRENT_BOOK_ID) {
    showAlert('Select text first', 'warning');
    return;
  }
  const payload = {
    book_id: CURRENT_BOOK_ID,
    page: currentVerseSelection.page,
    paragraph: parseInt(currentVerseSelection.paragraph),
    verse: parseInt(currentVerseSelection.verse),
    is_bold: !!isBold,
    is_italic: !!isItalic,
    content_role: contentRole,
    alignment_override: alignmentOverride,
  };
  const res = await fetch('/api/book-content-formats', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    showAlert('Could not save formatting', 'danger');
    return;
  }
  applyVerseFormatting(currentVerseSelection.matches, !!isBold, !!isItalic, contentRole, alignmentOverride);
  currentVerseSelection.isBold = !!isBold;
  currentVerseSelection.isItalic = !!isItalic;
  currentVerseSelection.contentRole = contentRole;
  currentVerseSelection.alignmentOverride = alignmentOverride;
  updateVerseFormatButtons(currentVerseSelection);
  showAlert('Format saved', 'success', 1200);
}

function applyVerseFormatting(elements, isBold, isItalic, contentRole = 'body', alignmentOverride = '') {
  elements.forEach(el => {
    el.dataset.isBold = isBold ? 'true' : 'false';
    el.dataset.isItalic = isItalic ? 'true' : 'false';
    el.dataset.contentRole = contentRole;
    el.dataset.alignmentOverride = alignmentOverride;
    el.classList.toggle('formatted-bold', isBold);
    el.classList.toggle('formatted-italic', isItalic);
    updateRoleClasses(el, contentRole);
    updateAlignmentClasses(el, alignmentOverride);
    const verse = el.closest('.sentence-verse');
    if (verse) {
      verse.dataset.isBold = isBold ? 'true' : 'false';
      verse.dataset.isItalic = isItalic ? 'true' : 'false';
      verse.dataset.contentRole = contentRole;
      verse.dataset.alignmentOverride = alignmentOverride;
      verse.classList.toggle('formatted-bold', isBold);
      verse.classList.toggle('formatted-italic', isItalic);
      updateRoleClasses(verse, contentRole);
      updateAlignmentClasses(verse, alignmentOverride);
    }
  });
}

function updateRoleClasses(el, contentRole) {
  ['title', 'subtitle', 'chapter', 'header', 'poetry'].forEach(role => {
    el.classList.toggle(`formatted-role-${role}`, contentRole === role);
  });
}

function updateAlignmentClasses(el, alignmentOverride) {
  ['left', 'center', 'right', 'justify'].forEach(alignment => {
    el.classList.toggle(`formatted-align-${alignment}`, alignmentOverride === alignment);
  });
}

async function selectTopicRangeEnd(fragment) {
  topicPickingEnd = false;
  updateTopicEndButton();
  const selection = getVerseSelection(fragment);
  let startId = parseInt(document.getElementById('topicStartContentId').value) || null;
  if (!startId) startId = selection.lowId;
  if (!startId || !selection.highId) {
    showAlert('Select a topic start first', 'warning');
    return;
  }
  await applyTopicRange(startId, selection.highId);
  showTab('#tabTopic');
}

async function applyTopicRange(startId, endId) {
  const params = new URLSearchParams({ start_id: startId, end_id: endId || startId });
  const data = await fetch(`/api/book-content/range?${params.toString()}`)
    .then(r => r.json())
    .catch(() => ({ error: 'Could not load selected range' }));
  if (data.error) {
    showAlert(data.error, 'danger');
    return;
  }
  setValue('topicChapter', data.chapter_name || '');
  setValue('topicPage', data.end_page && data.end_page !== data.page ? `${data.page}-${data.end_page}` : (data.page || CURRENT_PAGE || ''));
  setValue('topicPara', data.paragraph || '');
  setValue('topicVerse', data.verse || '');
  setValue('topicSelectedText', makeTextSnippet(data.content || ''));
  setValue('topicContentIds', (data.content_ids || []).join(','));
  setValue('topicStartContentId', data.start_content_id || startId);
  setValue('topicEndContentId', data.end_content_id || endId || startId);
  highlightTopicRange();
  saveTopicDraft();
}

function highlightTopicRange() {
  const startId = parseInt(document.getElementById('topicStartContentId')?.value) || null;
  const endId = parseInt(document.getElementById('topicEndContentId')?.value) || startId;
  document.querySelectorAll('.verse-fragment.selected-verse').forEach(el => {
    el.classList.remove('selected-verse');
  });
  if (!startId || !endId) return;
  const lowId = Math.min(startId, endId);
  const highId = Math.max(startId, endId);
  document.querySelectorAll('.verse-fragment').forEach(el => {
    const id = parseInt(el.dataset.contentId);
    if (id >= lowId && id <= highId) el.classList.add('selected-verse');
  });
}

function editFragment(fragment) {
  if (fragment.classList.contains('editing-fragment')) return;
  const original = fragment.dataset.rawContent || fragment.textContent.trim();
  fragment.classList.add('editing-fragment');
  fragment.contentEditable = 'true';
  fragment.textContent = original;
  fragment.focus();

  const range = document.createRange();
  range.selectNodeContents(fragment);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);

  let finished = false;
  const cleanup = () => {
    fragment.contentEditable = 'false';
    fragment.classList.remove('editing-fragment');
    fragment.removeEventListener('blur', save);
    fragment.removeEventListener('keydown', onKeydown);
  };
  const render = value => {
    fragment.dataset.rawContent = value;
    fragment.textContent = displayFragmentText(value, fragmentDisplayMode(fragment));
  };
  const cancel = () => {
    if (finished) return;
    finished = true;
    cleanup();
    render(original);
  };
  const save = async () => {
    if (finished) return;
    finished = true;
    const next = fragment.textContent.trim();
    cleanup();
    if (!next) {
      render(original);
      showAlert('Text cannot be empty', 'warning');
      return;
    }
    if (next === original) {
      render(original);
      return;
    }
    render(next);
    const res = await fetch(fragmentUpdateUrl(fragment), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: next }),
    }).then(r => r.json()).catch(() => ({ error: 'Save failed' }));
    if (res.error) {
      render(original);
      showAlert(res.error || 'Save failed', 'danger');
      return;
    }
    showAlert('Text updated', 'success', 1500);
  };
  const onKeydown = e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      save();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancel();
    }
  };

  fragment.addEventListener('blur', save);
  fragment.addEventListener('keydown', onKeydown);
}

function displayFragmentText(value, mode = CONTENT_MODE) {
  if (mode === 'paragraph') {
    return value;
  }
  if (mode === 'sentence' && value.endsWith('-')) {
    return value.slice(0, -1);
  }
  return `${value} `;
}

function fragmentUpdateUrl(fragment) {
  if (fragment.classList.contains('pamphlet-fragment')) {
    return `/api/pamphlet-content/${fragment.dataset.pamphletContentId}`;
  }
  return `/api/book-content/${fragment.dataset.contentId}`;
}

function fragmentDisplayMode(fragment) {
  if (fragment.classList.contains('pamphlet-fragment')) return 'paragraph';
  return fragment.dataset.contentMode || CONTENT_MODE;
}

function setValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value;
}

function resetDictionaryForm() {
  document.getElementById('dictForm')?.reset();
  clearDictionaryEditState();
  if (CURRENT_PAGE) setValue('dictPage', CURRENT_PAGE);
}

function clearDictionaryEditState({ preservePage = false } = {}) {
  const page = document.getElementById('dictPage')?.value || CURRENT_PAGE || '';
  ['dictEntryId', 'dictLookupId', 'dictLocationId'].forEach(id => setValue(id, ''));
  if (!preservePage && CURRENT_PAGE) setValue('dictPage', CURRENT_PAGE);
  if (preservePage) setValue('dictPage', page);
}

function resetReferenceForm() {
  document.getElementById('refForm')?.reset();
  currentRefEditId = null;
  setValue('refId', '');
  if (CURRENT_PAGE) setValue('refSrcPage', CURRENT_PAGE);
}

function resetCommentaryForm() {
  document.getElementById('commForm')?.reset();
  currentCommEditId = null;
  setValue('commId', '');
  if (CURRENT_PAGE) setValue('commPage', CURRENT_PAGE);
}

function resetReflectForm() {
  document.getElementById('reflectForm')?.reset();
  currentReflectEditId = null;
  setValue('reflectId', '');
  if (CURRENT_PAGE) setValue('reflectPage', CURRENT_PAGE);
}

function resetSourceForm() {
  document.getElementById('srcForm')?.reset();
  currentSourceEditId = null;
  setValue('srcId', '');
  if (CURRENT_PAGE) setValue('srcPage', CURRENT_PAGE);
  setSourceUrlFields(['']);
}

function combineVerseText(parts) {
  return parts.reduce((text, part) => {
    if (!part) return text;
    if (!text) return part;
    if (text.endsWith('-')) return text.slice(0, -1) + part;
    return `${text} ${part}`;
  }, '').replace(/\s+/g, ' ').trim();
}

/* ── Dictionary form (reading page quick entry) ────────────────────────────── */

document.getElementById('dictForm').addEventListener('submit', async function (e) {
  e.preventDefault();
  if (!CURRENT_BOOK_ID) { showAlert('Select a book first', 'warning'); return; }

  const dictEntryId = document.getElementById('dictEntryId').value;
  const dictLocationId = document.getElementById('dictLocationId').value;
  const word = document.getElementById('dictWord').value.trim();
  const meaning = document.getElementById('dictMeaning').value.trim();
  if (!word || !meaning) return;

  if (dictEntryId && dictLocationId) {
    const dictRes = await fetch(`/api/dictionary/${dictEntryId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        word_phrase: word,
        meaning,
        notes: document.getElementById('dictNotes').value.trim(),
      }),
    }).then(r => r.json());
    if (dictRes.error) { showAlert(dictRes.error, 'danger'); return; }

    const locRes = await fetch(`/api/book-locations/${dictLocationId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chapter: document.getElementById('dictChapter').value.trim(),
        page: document.getElementById('dictPage').value.trim() || CURRENT_PAGE,
        paragraph: parseInt(document.getElementById('dictPara').value) || null,
        line_number: parseInt(document.getElementById('dictLine').value) || null,
        line_text: document.getElementById('dictLineText').value.trim(),
      }),
    }).then(r => r.json());
    if (locRes.error) { showAlert(locRes.error, 'danger'); return; }

    const lookupId = document.getElementById('dictLookupId').value;
    if (lookupId) {
      const lookupRes = await fetch(`/api/dictionary-lookup/${lookupId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dictionary_id: parseInt(dictEntryId),
          book_location_id: parseInt(dictLocationId),
          rank: parseInt(document.getElementById('dictRank').value) || null,
        }),
      }).then(r => r.json());
      if (lookupRes.error) { showAlert(lookupRes.error, 'danger'); return; }
    }

    showAlert('Dictionary annotation updated', 'success');
    resetDictionaryForm();
    loadPageSummary();
    return;
  }

  // 1. Create dictionary entry
  const dictRes = await fetch('/api/dictionary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      word_phrase: word,
      meaning,
      notes: document.getElementById('dictNotes').value.trim(),
    }),
  }).then(r => r.json());

  if (dictRes.error) { showAlert(dictRes.error, 'danger'); return; }
  const dictId = dictRes.data.id;

  // 2. Create book location
  const locRes = await fetch('/api/book-locations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      book_id: CURRENT_BOOK_ID,
      chapter: document.getElementById('dictChapter').value.trim(),
      page: document.getElementById('dictPage').value.trim() || CURRENT_PAGE,
      paragraph: parseInt(document.getElementById('dictPara').value) || null,
      line_number: parseInt(document.getElementById('dictLine').value) || null,
      line_text: document.getElementById('dictLineText').value.trim(),
    }),
  }).then(r => r.json());

  if (locRes.error) { showAlert(locRes.error, 'danger'); return; }

  // 3. Link via lookup table
  await fetch('/api/dictionary-lookup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dictionary_id: dictId,
      book_location_id: locRes.data.id,
      rank: parseInt(document.getElementById('dictRank').value) || null,
    }),
  });

  showAlert(`"${word}" saved to dictionary`, 'success');
  resetDictionaryForm();
  loadPageSummary();
});

/* ── Book reference form ────────────────────────────────────────────────────── */

document.getElementById('refForm').addEventListener('submit', async function (e) {
  e.preventDefault();
  if (!CURRENT_BOOK_ID) { showAlert('Select a book first', 'warning'); return; }
  const refIdField = document.getElementById('refId').value.trim();
  const refId = currentRefEditId || refIdField || null;
  const targetBook = document.getElementById('refTargetBook').value;
  if (!targetBook) { showAlert('Select a target book', 'warning'); return; }

  const payload = {
    source_book_id: CURRENT_BOOK_ID,
    source_chapter: document.getElementById('refSrcChapter').value.trim(),
    source_page: document.getElementById('refSrcPage').value.trim() || CURRENT_PAGE,
    source_paragraph: parseInt(document.getElementById('refSrcPara').value) || null,
    source_verse: parseInt(document.getElementById('refSrcLine').value) || null,
    target_book_id: parseInt(targetBook),
    target_chapter: document.getElementById('refTgtChapter').value.trim(),
    target_page: document.getElementById('refTgtPage').value.trim(),
    target_paragraph: parseInt(document.getElementById('refTgtPara').value) || null,
    target_verse: parseInt(document.getElementById('refTgtLine').value) || null,
    quoted_text: document.getElementById('refQuoted').value.trim(),
    comments: document.getElementById('refComments').value.trim(),
    rank: parseInt(document.getElementById('refRank').value) || null,
  };

  const res = await fetch(refId ? `/api/references/${refId}` : '/api/references', {
    method: refId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert(refId ? 'Reference updated' : 'Reference saved', 'success');
  resetReferenceForm();
  loadPageSummary();
});

/* ── Commentary form ────────────────────────────────────────────────────────── */

document.getElementById('commForm').addEventListener('submit', async function (e) {
  e.preventDefault();
  saveCommentary();
});
document.getElementById('saveCommentaryBtn').addEventListener('click', saveCommentary);

async function saveCommentary() {
  if (!CURRENT_BOOK_ID) { showAlert('Select a book first', 'warning'); return; }
  const commIdField = document.getElementById('commId').value.trim();
  const commId = currentCommEditId || commIdField || null;
  const text = document.getElementById('commText').value.trim();
  if (!text) { showAlert('Commentary text is required', 'warning'); return; }

  const payload = {
    book_id: CURRENT_BOOK_ID,
    chapter: document.getElementById('commChapter').value.trim(),
    page: document.getElementById('commPage').value.trim() || CURRENT_PAGE,
    paragraph: parseInt(document.getElementById('commPara').value) || null,
    verse: parseInt(document.getElementById('commLine').value) || null,
    commentary_text: text,
    rank: parseInt(document.getElementById('commRank').value) || null,
  };

  const res = await fetch(commId ? `/api/commentary/${commId}` : '/api/commentary', {
    method: commId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json()).catch(() => ({ error: 'Commentary save failed' }));

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert(commId ? 'Commentary updated' : 'Commentary saved', 'success');
  resetCommentaryForm();
  loadPageSummary();
}

document.getElementById('reflectForm')?.addEventListener('submit', async function (e) {
  e.preventDefault();
  saveReflectPrompt();
});

async function saveReflectPrompt() {
  if (!CURRENT_BOOK_ID) { showAlert('Select a book first', 'warning'); return; }
  const reflectIdField = document.getElementById('reflectId').value.trim();
  const reflectId = currentReflectEditId || reflectIdField || null;
  const text = document.getElementById('reflectText').value.trim();
  if (!text) { showAlert('Reflect prompt is required', 'warning'); return; }

  const payload = {
    book_id: CURRENT_BOOK_ID,
    chapter: document.getElementById('reflectChapter').value.trim(),
    page: document.getElementById('reflectPage').value.trim() || CURRENT_PAGE,
    paragraph: parseInt(document.getElementById('reflectPara').value) || null,
    verse: parseInt(document.getElementById('reflectLine').value) || null,
    prompt_text: text,
    rank: parseInt(document.getElementById('reflectRank').value) || null,
  };

  const res = await fetch(reflectId ? `/api/reflect-prompts/${reflectId}` : '/api/reflect-prompts', {
    method: reflectId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json()).catch(() => ({ error: 'Reflect prompt save failed' }));

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert(reflectId ? 'Reflect prompt updated' : 'Reflect prompt saved', 'success');
  resetReflectForm();
  loadPageSummary();
}

/* ── Topic form ────────────────────────────────────────────────────────────── */

function loadTopicOptions() {
  const select = document.getElementById('topicSelect');
  if (!select) return;
  return fetch('/api/topics').then(r => r.json()).then(topics => {
    select.innerHTML = '<option value="">— Select —</option>';
    topics.forEach(topic => {
      const option = document.createElement('option');
      option.value = topic.id;
      option.textContent = topic.name;
      select.appendChild(option);
    });
  });
}

function setTopicEditMode(isEdit) {
  const badge = document.getElementById('topicEditBadge');
  const submitBtn = document.getElementById('topicSubmitBtn');
  if (badge) badge.classList.toggle('d-none', !isEdit);
  if (submitBtn) {
    submitBtn.innerHTML = isEdit
      ? '<i class="bi bi-pencil-square me-1"></i>Save Tag Changes'
      : '<i class="bi bi-tag me-1"></i>Apply Topic';
  }
}

function updateTopicEndButton() {
  const btn = document.getElementById('topicSetEndBtn');
  if (!btn) return;
  btn.classList.toggle('active', topicPickingEnd);
  btn.innerHTML = topicPickingEnd
    ? '<i class="bi bi-cursor-fill me-1"></i>Click End Text'
    : '<i class="bi bi-cursor me-1"></i>Set End';
}

function readTopicDraft() {
  return {
    linkId: document.getElementById('topicLinkId')?.value || '',
    select: document.getElementById('topicSelect')?.value || '',
    newName: document.getElementById('topicNewName')?.value || '',
    notes: document.getElementById('topicNotes')?.value || '',
    rank: document.getElementById('topicRank')?.value || '',
    chapter: document.getElementById('topicChapter')?.value || '',
    page: document.getElementById('topicPage')?.value || '',
    para: document.getElementById('topicPara')?.value || '',
    verse: document.getElementById('topicVerse')?.value || '',
    selectedText: document.getElementById('topicSelectedText')?.value || '',
    contentIds: document.getElementById('topicContentIds')?.value || '',
    startContentId: document.getElementById('topicStartContentId')?.value || '',
    endContentId: document.getElementById('topicEndContentId')?.value || '',
  };
}

function saveTopicDraft() {
  const draft = readTopicDraft();
  if (!draft.startContentId && !draft.selectedText && !draft.newName && !draft.notes && !draft.select) return;
  localStorage.setItem(TOPIC_DRAFT_KEY, JSON.stringify(draft));
}

function clearTopicDraft() {
  localStorage.removeItem(TOPIC_DRAFT_KEY);
}

function restoreTopicDraft() {
  const raw = localStorage.getItem(TOPIC_DRAFT_KEY);
  if (!raw) return;
  let draft = null;
  try {
    draft = JSON.parse(raw);
  } catch {
    clearTopicDraft();
    return;
  }
  setValue('topicLinkId', draft.linkId || '');
  setValue('topicSelect', draft.select || '');
  setValue('topicNewName', draft.newName || '');
  setValue('topicNotes', draft.notes || '');
  setValue('topicRank', draft.rank || '');
  setValue('topicChapter', draft.chapter || '');
  setValue('topicPage', draft.page || CURRENT_PAGE || '');
  setValue('topicPara', draft.para || '');
  setValue('topicVerse', draft.verse || '');
  setValue('topicSelectedText', draft.selectedText || '');
  setValue('topicContentIds', draft.contentIds || '');
  setValue('topicStartContentId', draft.startContentId || '');
  setValue('topicEndContentId', draft.endContentId || draft.startContentId || '');
  currentTopicLinkEditId = draft.linkId || null;
  setTopicEditMode(!!draft.linkId);
  highlightTopicRange();
}

function resetTopicEditor() {
  currentTopicLinkEditId = null;
  setValue('topicLinkId', '');
  setValue('topicNewName', '');
  setValue('topicNotes', '');
  setTopicEditMode(false);
  saveTopicDraft();
}

document.getElementById('topicSetEndBtn')?.addEventListener('click', () => {
  if (!document.getElementById('topicStartContentId').value) {
    showAlert('Select the start text first', 'warning');
    return;
  }
  topicPickingEnd = !topicPickingEnd;
  updateTopicEndButton();
});

document.getElementById('topicClearRangeBtn')?.addEventListener('click', () => {
  topicPickingEnd = false;
  updateTopicEndButton();
  currentTopicLinkEditId = null;
  ['topicLinkId', 'topicContentIds', 'topicStartContentId', 'topicEndContentId',
   'topicChapter', 'topicPage', 'topicPara', 'topicVerse', 'topicSelectedText',
   'topicNewName', 'topicNotes', 'topicRank'].forEach(id => setValue(id, ''));
  document.querySelectorAll('.verse-fragment.selected-verse').forEach(el => el.classList.remove('selected-verse'));
  setTopicEditMode(false);
  clearTopicDraft();
});

['topicSelect', 'topicNewName', 'topicNotes', 'topicRank'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', saveTopicDraft);
  document.getElementById(id)?.addEventListener('change', saveTopicDraft);
});

document.getElementById('topicForm').addEventListener('submit', async function (e) {
  e.preventDefault();
  const linkIdField = document.getElementById('topicLinkId').value.trim();
  const editingLinkId = currentTopicLinkEditId || linkIdField || null;
  const startContentId = parseInt(document.getElementById('topicStartContentId').value) || null;
  const endContentId = parseInt(document.getElementById('topicEndContentId').value) || startContentId;
  const ids = document.getElementById('topicContentIds').value
    .split(',')
    .map(value => parseInt(value))
    .filter(Boolean);
  if (!startContentId && !ids.length) { showAlert('Select text first', 'warning'); return; }

  let topicId = parseInt(document.getElementById('topicSelect').value) || null;
  const newName = document.getElementById('topicNewName').value.trim();
  if (!topicId && newName) {
    const topicRes = await fetch('/api/topics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName }),
    }).then(r => r.json());
    if (topicRes.error) { showAlert(topicRes.error, 'danger'); return; }
    topicId = topicRes.data.id;
    loadTopicOptions();
  }
  if (!topicId) { showAlert('Choose or create a topic', 'warning'); return; }

  const notes = document.getElementById('topicNotes').value.trim();
  const res = editingLinkId
    ? await fetch(`/api/content-topics/${editingLinkId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic_id: topicId,
        start_content_id: startContentId,
        end_content_id: endContentId,
        notes,
        rank: parseInt(document.getElementById('topicRank').value) || null,
      }),
    }).then(r => r.json())
    : await fetch('/api/content-topics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic_id: topicId,
        start_content_id: startContentId || Math.min(...ids),
        end_content_id: endContentId || Math.max(...ids),
        notes,
        rank: parseInt(document.getElementById('topicRank').value) || null,
      }),
    }).then(r => r.json());

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert(editingLinkId ? 'Tag updated' : 'Topic applied', 'success', 1500);
  resetTopicEditor();
  clearTopicDraft();
  loadPageSummary();
});

/* ── Other sources form ─────────────────────────────────────────────────────── */

document.getElementById('srcForm').addEventListener('submit', async function (e) {
  e.preventDefault();
  const srcIdField = document.getElementById('srcId').value.trim();
  const srcId = currentSourceEditId || srcIdField || null;
  const name = document.getElementById('srcName').value.trim();
  if (!name) return;

  const payload = {
    book_id: CURRENT_BOOK_ID,
    chapter: document.getElementById('srcChapter').value.trim(),
    page: document.getElementById('srcPage').value.trim() || CURRENT_PAGE,
    paragraph: parseInt(document.getElementById('srcPara').value) || null,
    verse: parseInt(document.getElementById('srcVerse').value) || null,
    name,
    source_type: document.getElementById('srcType').value,
    author: document.getElementById('srcAuthor').value.trim(),
    urls: sourceReferenceValues(),
    notes: document.getElementById('srcNotes').value.trim(),
    rank: parseInt(document.getElementById('srcRank').value) || null,
  };

  const res = await fetch(srcId ? `/api/sources/${srcId}` : '/api/sources', {
    method: srcId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert(srcId ? 'Source updated' : 'Source saved', 'success');
  resetSourceForm();
  loadPageSummary();
});

function setSourceUrlFields(urls = ['']) {
  const container = document.getElementById('srcUrlsContainer');
  if (!container) return;
  container.innerHTML = '';
  const values = urls.length ? urls : [''];
  values.forEach(url => addSourceUrlField(url));
}

function addSourceUrlField(value = '') {
  const container = document.getElementById('srcUrlsContainer');
  if (!container) return;
  const row = document.createElement('div');
  row.className = 'input-group input-group-sm source-url-field';
  row.innerHTML = `
    <input type="text" class="form-control source-url-input" value="${escAttr(value)}">
    <button class="btn btn-outline-secondary" type="button" aria-label="Remove reference">
      <i class="bi bi-x-lg"></i>
    </button>`;
  row.querySelector('button').addEventListener('click', () => {
    row.remove();
    if (!container.querySelector('.source-url-input')) addSourceUrlField();
  });
  container.appendChild(row);
}

function sourceReferenceValues() {
  return [...document.querySelectorAll('#srcUrlsContainer .source-url-input')]
    .map(input => input.value.trim())
    .filter(Boolean);
}

function renderSourceReferences(urls = []) {
  const values = urls.map(url => String(url || '').trim()).filter(Boolean);
  if (!values.length) return '';
  return `<div class="source-reference-list mb-1">${values.map(url => (
    `<div class="source-reference-line">${escHtml(url)}</div>`
  )).join('')}</div>`;
}

/* ── Split selected text ───────────────────────────────────────────────────── */

document.getElementById('insertSplitMarkerBtn')?.addEventListener('click', () => {
  const field = document.getElementById('splitMarkerText');
  if (!field) return;
  const start = field.selectionStart ?? field.value.length;
  const end = field.selectionEnd ?? start;
  field.value = `${field.value.slice(0, start)}|${field.value.slice(end)}`;
  field.focus();
  field.selectionStart = field.selectionEnd = start + 1;
});

document.getElementById('splitForm')?.addEventListener('submit', async function (e) {
  e.preventDefault();
  const contentId = document.getElementById('splitContentId').value;
  const markerText = document.getElementById('splitMarkerText').value;
  if (!contentId) {
    showAlert('Select text to split first', 'warning');
    return;
  }
  if ((markerText.match(/\|/g) || []).length !== 1) {
    showAlert('Place exactly one | where the text should split', 'warning');
    return;
  }

  const res = await fetch(`/api/book-content/${contentId}/split`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ marker_text: markerText }),
  }).then(r => r.json()).catch(() => ({ error: 'Split failed' }));

  if (res.error) {
    showAlert(res.error || 'Split failed', 'danger');
    return;
  }
  showAlert('Text split', 'success', 1200);
  location.reload();
});

/* ── Add content modal (save button) ───────────────────────────────────────── */

document.getElementById('saveContentBtn').addEventListener('click', async function () {
  if (!CURRENT_BOOK_ID) { showAlert('Select a book first', 'warning'); return; }
  const content = document.getElementById('acContent').value.trim();
  if (!content) { showAlert('Content is required', 'warning'); return; }

  const payload = {
    book_id: CURRENT_BOOK_ID,
    chapter: document.getElementById('acChapter').value.trim(),
    page: document.getElementById('acPage').value.trim() || CURRENT_PAGE,
    paragraph: parseInt(document.getElementById('acPara').value) || null,
    line: parseInt(document.getElementById('acLine').value) || null,
    content,
  };

  const res = await fetch('/api/book-content', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert('Content saved', 'success');
  bootstrap.Modal.getInstance(document.getElementById('addContentModal')).hide();
  document.getElementById('addContentForm').reset();
  // Refresh page content area
  location.reload();
});

/* ── Pre-populate page field in entry forms ─────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  updateVerseFormatButtons();
  if (CURRENT_PAGE) {
    ['dictPage', 'refSrcPage', 'commPage', 'reflectPage', 'srcPage'].forEach(id => {
      const el = document.getElementById(id);
      if (el && !el.value) el.value = CURRENT_PAGE;
    });
  }
  loadPageFormat();
  loadPageSummary();
  loadPamphletOptions();
  setSourceUrlFields(['']);
  Promise.resolve(loadTopicOptions()).then(() => {
    setTopicEditMode(false);
    restoreTopicDraft();
  });
  updateTopicEndButton();

  document.querySelectorAll('#entryTabs [data-bs-toggle="tab"]').forEach(tab => {
    tab.addEventListener('shown.bs.tab', event => {
      const target = event.target.getAttribute('data-bs-target');
      if (target) localStorage.setItem(ACTIVE_TAB_KEY, target);
    });
  });
  document.querySelectorAll('#bookPaneTabs [data-bs-toggle="tab"]').forEach(tab => {
    tab.addEventListener('shown.bs.tab', event => {
      const target = event.target.getAttribute('data-bs-target');
      if (target) localStorage.setItem(BOOK_PANE_TAB_KEY, target);
    });
  });
  const activeBookPaneTarget = localStorage.getItem(BOOK_PANE_TAB_KEY);
  if (activeBookPaneTarget) {
    const trigger = document.querySelector(`#bookPaneTabs [data-bs-target="${activeBookPaneTarget}"]`);
    if (trigger) bootstrap.Tab.getOrCreateInstance(trigger).show();
  }
  const activeTarget = localStorage.getItem(ACTIVE_TAB_KEY);
  if (activeTarget) {
    const trigger = document.querySelector(`#entryTabs [data-bs-target="${activeTarget}"]`);
    if (trigger) bootstrap.Tab.getOrCreateInstance(trigger).show();
  }
  openPamphletFromUrl();
});
