/**
 * BB Study – Reading / index page logic.
 * Requires CURRENT_BOOK_ID and CURRENT_PAGE to be set by the template.
 */

/* ── Page navigation ───────────────────────────────────────────────────────── */

document.getElementById('loadPageBtn').addEventListener('click', loadPage);
document.getElementById('pageInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') loadPage();
});
document.getElementById('bookSelect').addEventListener('change', function () {
  const bookId = this.value;
  if (bookId) {
    persistSetting('current_book_id', bookId).then(() => location.reload());
  }
});

function loadPage() {
  const page = document.getElementById('pageInput').value.trim();
  if (!page) return;
  persistSetting('current_page', page).then(() => location.reload());
}

function persistSetting(key, value) {
  return fetch(`/api/settings/${key}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: String(value) }),
  });
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

      // Commentary
      if (data.commentary && data.commentary.length) {
        data.commentary.forEach(c => {
          summaryEl.appendChild(makeSummaryCard('Commentary', 'commentary',
            `<p class="mb-1">${escHtml(c.commentary_text)}</p>
             <small class="text-muted">Ch: ${escHtml(c.chapter || '—')} · Para: ${c.paragraph || '—'} · Line: ${c.line || '—'}</small>`,
            c.id, 'commentary'));
        });
      }

      // Book references
      if (data.references && data.references.length) {
        data.references.forEach(r => {
          summaryEl.appendChild(makeSummaryCard('Book Reference', 'reference',
            `<p class="mb-1 fst-italic">${escHtml(r.quoted_text || '')}</p>
             <p class="mb-0 small">→ <strong>${escHtml(r.target_book_title || '')}</strong>
               Ch: ${escHtml(r.target_chapter || '—')} · Pg: ${escHtml(r.target_page || '—')}</p>
             ${r.comments ? `<p class="text-muted small mb-0">${escHtml(r.comments)}</p>` : ''}`,
            r.id, 'references'));
        });
      }

      // Dictionary lookups
      if (data.dictionary && data.dictionary.length) {
        data.dictionary.forEach(d => {
          summaryEl.appendChild(makeSummaryCard('Dictionary', 'dictionary',
            `<strong>${escHtml(d.word_phrase || '')}</strong>: ${escHtml(d.meaning || '')}`,
            d.id, 'dictionary-lookup'));
        });
      }

      if (!summaryEl.children.length) {
        summaryEl.innerHTML = '<p class="text-muted small col-12">No annotations for this page yet.</p>';
      }
    })
    .catch(() => {
      const summaryEl = document.getElementById('pageSummary');
      if (summaryEl) summaryEl.innerHTML = '<p class="text-danger small col-12">Failed to load page summary.</p>';
    });
}

function makeSummaryCard(label, typeClass, bodyHtml, id, endpoint) {
  const col = document.createElement('div');
  col.className = 'col-md-6 col-lg-4';
  col.innerHTML = `
    <div class="card summary-card ${typeClass} h-100">
      <div class="card-header d-flex justify-content-between align-items-center py-1 px-2">
        <small class="fw-semibold text-uppercase">${label}</small>
        <button class="btn btn-sm btn-outline-danger border-0 py-0"
                onclick="deleteSummaryItem('${endpoint}', ${id})" title="Delete">
          <i class="bi bi-trash"></i>
        </button>
      </div>
      <div class="card-body py-2 px-2 small">${bodyHtml}</div>
    </div>`;
  return col;
}

function deleteSummaryItem(endpoint, id) {
  if (!confirm('Delete this item?')) return;
  fetch(`/api/${endpoint}/${id}`, { method: 'DELETE' })
    .then(() => loadPageSummary());
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ── Dictionary form (reading page quick entry) ────────────────────────────── */

document.getElementById('dictForm').addEventListener('submit', async function (e) {
  e.preventDefault();
  if (!CURRENT_BOOK_ID) { showAlert('Select a book first', 'warning'); return; }

  const word = document.getElementById('dictWord').value.trim();
  const meaning = document.getElementById('dictMeaning').value.trim();
  if (!word || !meaning) return;

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
  const targetBook = document.getElementById('refTargetBook').value;
  if (!targetBook) { showAlert('Select a target book', 'warning'); return; }

  const payload = {
    source_book_id: CURRENT_BOOK_ID,
    source_chapter: document.getElementById('refSrcChapter').value.trim(),
    source_page: document.getElementById('refSrcPage').value.trim() || CURRENT_PAGE,
    source_paragraph: parseInt(document.getElementById('refSrcPara').value) || null,
    source_line: parseInt(document.getElementById('refSrcLine').value) || null,
    target_book_id: parseInt(targetBook),
    target_chapter: document.getElementById('refTgtChapter').value.trim(),
    target_page: document.getElementById('refTgtPage').value.trim(),
    target_paragraph: parseInt(document.getElementById('refTgtPara').value) || null,
    target_line: parseInt(document.getElementById('refTgtLine').value) || null,
    quoted_text: document.getElementById('refQuoted').value.trim(),
    comments: document.getElementById('refComments').value.trim(),
  };

  const res = await fetch('/api/references', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert('Reference saved', 'success');
  this.reset();
  loadPageSummary();
});

/* ── Commentary form ────────────────────────────────────────────────────────── */

document.getElementById('commForm').addEventListener('submit', async function (e) {
  e.preventDefault();
  if (!CURRENT_BOOK_ID) { showAlert('Select a book first', 'warning'); return; }
  const text = document.getElementById('commText').value.trim();
  if (!text) return;

  const payload = {
    book_id: CURRENT_BOOK_ID,
    chapter: document.getElementById('commChapter').value.trim(),
    page: document.getElementById('commPage').value.trim() || CURRENT_PAGE,
    paragraph: parseInt(document.getElementById('commPara').value) || null,
    line: parseInt(document.getElementById('commLine').value) || null,
    commentary_text: text,
  };

  const res = await fetch('/api/commentary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert('Commentary saved', 'success');
  this.reset();
  loadPageSummary();
});

/* ── Other sources form ─────────────────────────────────────────────────────── */

document.getElementById('srcForm').addEventListener('submit', async function (e) {
  e.preventDefault();
  const name = document.getElementById('srcName').value.trim();
  if (!name) return;

  const payload = {
    name,
    source_type: document.getElementById('srcType').value,
    author: document.getElementById('srcAuthor').value.trim(),
    url: document.getElementById('srcUrl').value.trim(),
    notes: document.getElementById('srcNotes').value.trim(),
  };

  const res = await fetch('/api/sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  if (res.error) { showAlert(res.error, 'danger'); return; }
  showAlert('Source saved', 'success');
  this.reset();
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
  if (CURRENT_PAGE) {
    ['dictPage', 'refSrcPage', 'commPage'].forEach(id => {
      const el = document.getElementById(id);
      if (el && !el.value) el.value = CURRENT_PAGE;
    });
  }
  loadPageSummary();
});
