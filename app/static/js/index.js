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
  if (status) status.textContent = 'Loading...';
  if (empty) empty.classList.add('d-none');
  document.querySelector('.pamphlet-reader-search')?.classList.add('d-none');
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
        ${pageRows.map(row => `<p>${escHtml(row.content || '')}</p>`).join('')}
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
            `<p class="mb-1">${escHtml(c.commentary_text)}</p>
             ${loc ? `<small class="text-muted">${escHtml(loc)}</small>` : ''}`,
            c.id, 'commentary', 'commentary'));
        });
      }

      // Book references
      if (data.references && data.references.length) {
        data.references.forEach(r => {
          summaryCards.push(makeSummaryCard('Book Reference', 'reference',
            `<p class="mb-1 fst-italic">${escHtml(r.quoted_text || '')}</p>
             <p class="mb-0 small">→ <strong>${escHtml(r.target_book_title || '')}</strong>
               Ch: ${escHtml(r.target_chapter || '—')} · Pg: ${escHtml(r.target_page || '—')}</p>
             ${r.comments ? `<p class="text-muted small mb-0">${escHtml(r.comments)}</p>` : ''}`,
            r.id, 'references', 'reference'));
        });
      }

      // Other references / sources
      if (data.sources && data.sources.length) {
        data.sources.forEach(s => {
          const ref = s.url ? `<p class="mb-1">${escHtml(s.url)}</p>` : '';
          summaryCards.push(makeSummaryCard('Other Ref', 'reference',
            `<div class="mb-1"><span class="badge text-bg-secondary">${escHtml(s.source_type || 'other')}</span></div>
             <p class="mb-1 fw-semibold">${escHtml(s.name || '')}</p>
             ${ref}
             ${s.notes ? `<p class="text-muted small mb-0">${escHtml(s.notes)}</p>` : ''}`,
            s.id, 'sources', 'source'));
        });
      }

      // Dictionary lookups
      if (data.dictionary && data.dictionary.length) {
        summaryCards.push(makeDictionarySummaryCard(data.dictionary));
      }

      // Topic tags linked to content on this page
      if (data.topics && data.topics.length) {
        data.topics.forEach(link => {
          const loc = `p. ${escHtml(link.page || '')} · ¶${link.paragraph || ''} · v${link.verse || ''}`;
          summaryCards.push(makeSummaryCard('Tag', 'reference',
            `<div class="mb-1"><span class="badge text-bg-secondary">${escHtml(link.topic_name || '')}</span></div>
             <p class="mb-1 small text-muted">${loc}</p>
             <p class="mb-1 topic-snippet">${escHtml(makeTextSnippet(link.content || ''))}</p>
             ${link.notes ? `<p class="text-muted small mb-0">${escHtml(link.notes)}</p>` : ''}`,
            link.id, 'content-topics', 'topic-link'));
        });
      }

      if (!summaryCards.length) {
        summaryEl.innerHTML = '<p class="text-muted small mb-0">No annotations for this page yet.</p>';
        return;
      }
      renderBalancedSummaryCards(summaryEl, summaryCards);
    })
    .catch(() => {
      const summaryEl = document.getElementById('pageSummary');
      if (summaryEl) summaryEl.innerHTML = '<p class="text-danger small mb-0">Failed to load page summary.</p>';
    });
}

function makeSummaryCard(label, typeClass, bodyHtml, id, endpoint, annotationType) {
  const card = document.createElement('div');
  card.className = `card summary-card ${typeClass} annotation-card`;
  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');
  card.dataset.annotationType = annotationType;
  card.dataset.id = id;
  card.innerHTML = `
      <div class="card-header d-flex justify-content-between align-items-center py-1 px-2">
        <small class="fw-semibold text-uppercase">${label}</small>
        <button class="btn btn-sm btn-outline-danger border-0 py-0"
                onclick="event.stopPropagation(); deleteSummaryItem('${endpoint}', ${id})" title="Delete">
          <i class="bi bi-trash"></i>
        </button>
      </div>
      <div class="card-body py-2 px-2 small">${bodyHtml}</div>`;
  return card;
}

function makeDictionarySummaryCard(entries) {
  const card = document.createElement('div');
  card.className = 'card summary-card dictionary';
  const rows = entries.map(entry => `
    <div class="dictionary-summary-row d-flex align-items-start gap-2">
      <button class="dictionary-summary-entry text-start flex-grow-1" type="button"
              data-annotation-type="dictionary" data-id="${entry.id}">
        <span class="fw-semibold">${escHtml(entry.word_phrase || '')}</span>
        <span class="text-muted"> — ${escHtml(makeTextSnippet(entry.meaning || '', ''))}</span>
      </button>
      <button class="btn btn-sm btn-outline-danger border-0 py-0 dictionary-summary-delete"
              type="button" data-id="${entry.id}" title="Delete">
        <i class="bi bi-trash"></i>
      </button>
    </div>`).join('');
  card.innerHTML = `
      <div class="card-header py-1 px-2">
        <small class="fw-semibold text-uppercase">Dictionary</small>
      </div>
      <div class="card-body py-2 px-2 small dictionary-summary-list">${rows}</div>`;
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

  measureSummaryCards(cards, columns[0]).forEach(({ card }) => {
    const shortestColumn = columns.reduce((shortest, column) =>
      column.scrollHeight < shortest.scrollHeight ? column : shortest);
    shortestColumn.appendChild(card);
  });
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
  return measured.sort((a, b) => b.height - a.height);
}

function getSummaryColumnCount(summaryEl) {
  const columns = getComputedStyle(summaryEl).gridTemplateColumns
    .split(' ')
    .filter(Boolean);
  return Math.max(1, columns.length || 1);
}

document.addEventListener('click', e => {
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
    showTab('#tabComm');
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
    setValue('srcAuthor', source.author || '');
    setValue('srcUrl', source.url || '');
    setValue('srcNotes', source.notes || '');
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
  const fragment = e.target.closest('.verse-fragment');
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
  setValue('refSrcChapter', selection.chapter);
  setValue('refSrcPage', selection.page);
  setValue('refSrcPara', selection.paragraph);
  setValue('refSrcLine', selection.verse);
  setValue('refQuoted', selection.fullText);
  setValue('commChapter', selection.chapter);
  setValue('commPage', selection.page);
  setValue('commPara', selection.paragraph);
  setValue('commLine', selection.verse);
  setValue('topicChapter', selection.chapter);
  setValue('topicPage', selection.page);
  setValue('topicPara', selection.paragraph);
  setValue('topicVerse', selection.verse);
  setValue('topicSelectedText', makeTextSnippet(selection.fullText));
  setValue('topicContentIds', selection.ids.join(','));
  setValue('topicStartContentId', selection.lowId || '');
  setValue('topicEndContentId', selection.highId || '');
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
    isBold: matches.some(el => el.dataset.isBold === 'true' || el.classList.contains('formatted-bold')),
    isItalic: matches.some(el => el.dataset.isItalic === 'true' || el.classList.contains('formatted-italic')),
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
}

async function toggleSelectedVerseFormat(kind) {
  if (!currentVerseSelection || !CURRENT_BOOK_ID) {
    showAlert('Select a verse first', 'warning');
    return;
  }
  const nextBold = kind === 'bold' ? !currentVerseSelection.isBold : currentVerseSelection.isBold;
  const nextItalic = kind === 'italic' ? !currentVerseSelection.isItalic : currentVerseSelection.isItalic;
  const payload = {
    book_id: CURRENT_BOOK_ID,
    page: currentVerseSelection.page,
    paragraph: parseInt(currentVerseSelection.paragraph),
    verse: parseInt(currentVerseSelection.verse),
    is_bold: nextBold,
    is_italic: nextItalic,
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
  applyVerseFormatting(currentVerseSelection.matches, nextBold, nextItalic);
  currentVerseSelection.isBold = nextBold;
  currentVerseSelection.isItalic = nextItalic;
  updateVerseFormatButtons(currentVerseSelection);
}

function applyVerseFormatting(elements, isBold, isItalic) {
  elements.forEach(el => {
    el.dataset.isBold = isBold ? 'true' : 'false';
    el.dataset.isItalic = isItalic ? 'true' : 'false';
    el.classList.toggle('formatted-bold', isBold);
    el.classList.toggle('formatted-italic', isItalic);
    const verse = el.closest('.sentence-verse');
    if (verse) {
      verse.dataset.isBold = isBold ? 'true' : 'false';
      verse.dataset.isItalic = isItalic ? 'true' : 'false';
      verse.classList.toggle('formatted-bold', isBold);
      verse.classList.toggle('formatted-italic', isItalic);
    }
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
    fragment.textContent = displayFragmentText(value);
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
    const res = await fetch(`/api/book-content/${fragment.dataset.contentId}`, {
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

function displayFragmentText(value) {
  if (typeof CONTENT_MODE !== 'undefined' && CONTENT_MODE === 'sentence' && value.endsWith('-')) {
    return value.slice(0, -1);
  }
  return `${value} `;
}

function setValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value;
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

    showAlert('Dictionary annotation updated', 'success');
    this.reset();
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
    body: JSON.stringify({ dictionary_id: dictId, book_location_id: locRes.data.id }),
  });

  showAlert(`"${word}" saved to dictionary`, 'success');
  this.reset();
  document.getElementById('dictPage').value = CURRENT_PAGE || '';
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
  };

  const res = await fetch(refId ? `/api/references/${refId}` : '/api/references', {
    method: refId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert(refId ? 'Reference updated' : 'Reference saved', 'success');
  this.reset();
  currentRefEditId = null;
  setValue('refId', '');
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
  };

  const res = await fetch(commId ? `/api/commentary/${commId}` : '/api/commentary', {
    method: commId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json()).catch(() => ({ error: 'Commentary save failed' }));

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert(commId ? 'Commentary updated' : 'Commentary saved', 'success');
  document.getElementById('commForm').reset();
  currentCommEditId = null;
  setValue('commId', '');
  if (CURRENT_PAGE) setValue('commPage', CURRENT_PAGE);
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
   'topicNewName', 'topicNotes'].forEach(id => setValue(id, ''));
  document.querySelectorAll('.verse-fragment.selected-verse').forEach(el => el.classList.remove('selected-verse'));
  setTopicEditMode(false);
  clearTopicDraft();
});

['topicSelect', 'topicNewName', 'topicNotes'].forEach(id => {
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
    page: CURRENT_PAGE,
    name,
    source_type: document.getElementById('srcType').value,
    author: document.getElementById('srcAuthor').value.trim(),
    url: document.getElementById('srcUrl').value.trim(),
    notes: document.getElementById('srcNotes').value.trim(),
  };

  const res = await fetch(srcId ? `/api/sources/${srcId}` : '/api/sources', {
    method: srcId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert(srcId ? 'Source updated' : 'Source saved', 'success');
  this.reset();
  currentSourceEditId = null;
  setValue('srcId', '');
  loadPageSummary();
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
    ['dictPage', 'refSrcPage', 'commPage'].forEach(id => {
      const el = document.getElementById(id);
      if (el && !el.value) el.value = CURRENT_PAGE;
    });
  }
  loadPageSummary();
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
