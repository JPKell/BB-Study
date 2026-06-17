document.addEventListener('DOMContentLoaded', () => {
  const state = {
    tables: [],
    table: null,
    columns: [],
    primaryKey: [],
    rows: [],
    page: 1,
    pages: 1,
    total: 0,
    perPage: 50,
    sorts: [],
    selected: new Set(),
    selectedColumn: null,
    pending: new Map(),
    isDragging: false,
    dragColumn: null,
  };

  const els = {
    tableList: document.getElementById('dbTableList'),
    title: document.getElementById('dbTableTitle'),
    meta: document.getElementById('dbTableMeta'),
    filter: document.getElementById('dbFilterInput'),
    clearFilter: document.getElementById('dbClearFilterBtn'),
    head: document.getElementById('dbTableHead'),
    body: document.getElementById('dbTableBody'),
    selectedBadge: document.getElementById('dbSelectedBadge'),
    pendingBadge: document.getElementById('dbPendingBadge'),
    bulkValue: document.getElementById('dbBulkValueInput'),
    applyBulk: document.getElementById('dbApplyBulkBtn'),
    commit: document.getElementById('dbCommitBtn'),
    cancel: document.getElementById('dbCancelBtn'),
    prev: document.getElementById('dbPrevBtn'),
    next: document.getElementById('dbNextBtn'),
    pageSummary: document.getElementById('dbPageSummary'),
    pageSize: document.getElementById('dbPageSize'),
  };

  function cellKey(pk, column) {
    return `${JSON.stringify(pk)}::${column}`;
  }

  function pkForRow(row) {
    return Object.fromEntries(state.primaryKey.map((field) => [field, row[field]]));
  }

  function sortQuery() {
    return state.sorts.map((sort) => `${sort.column}:${sort.direction}`).join(',');
  }

  function displayValue(value) {
    if (value === null || value === undefined) return '';
    return String(value);
  }

  function setBusy(isBusy) {
    document.querySelector('[data-db-browser]')?.classList.toggle('db-loading', isBusy);
  }

  function updateBadges() {
    els.selectedBadge.textContent = `${state.selected.size} selected`;
    els.pendingBadge.textContent = `${state.pending.size} pending`;
    els.commit.disabled = state.pending.size === 0;
    els.cancel.disabled = state.pending.size === 0 && state.selected.size === 0;
  }

  function pendingColumns() {
    return new Set(Array.from(state.pending.values()).map((pending) => pending.column));
  }

  function canSelectColumn(column) {
    const columns = pendingColumns();
    if (columns.size === 0 || columns.has(column)) return true;
    showAlert('Commit or cancel pending changes before editing another column.', 'warning');
    return false;
  }

  function clearSelection() {
    state.selected.clear();
    state.selectedColumn = null;
    els.body.querySelectorAll('.db-cell-selected').forEach((cell) => {
      cell.classList.remove('db-cell-selected');
    });
    updateBadges();
  }

  function selectCell(cell, selected = true) {
    const key = cell.dataset.key;
    const column = cell.dataset.column;
    if (!canSelectColumn(column)) return false;
    if (state.selectedColumn && state.selectedColumn !== column) {
      clearSelection();
    }
    state.selectedColumn = column;
    if (selected) {
      state.selected.add(key);
    } else {
      state.selected.delete(key);
      if (state.selected.size === 0) state.selectedColumn = null;
    }
    cell.classList.toggle('db-cell-selected', state.selected.has(key));
    updateBadges();
    return true;
  }

  function loadEditorFromCell(cell) {
    els.bulkValue.value = cell.textContent || '';
    els.bulkValue.focus();
    els.bulkValue.select();
  }

  function renderTableList() {
    els.tableList.replaceChildren(...state.tables.map((table) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `list-group-item list-group-item-action ${table.name === state.table ? 'active' : ''}`;
      button.dataset.table = table.name;
      button.innerHTML = '';
      const name = document.createElement('span');
      name.className = 'db-table-name';
      name.textContent = table.name;
      const meta = document.createElement('small');
      meta.textContent = `${table.column_count} fields`;
      button.append(name, meta);
      button.addEventListener('click', () => selectTable(table.name));
      return button;
    }));
  }

  function renderHeader() {
    const row = document.createElement('tr');
    for (const column of state.columns) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.className = column.primary_key ? 'db-primary-key' : '';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'db-sort-button';
      button.title = `Sort ${column.name}`;
      const label = document.createElement('span');
      label.textContent = column.name;
      button.appendChild(label);
      const sortIndex = state.sorts.findIndex((sort) => sort.column === column.name);
      if (sortIndex >= 0) {
        const sort = state.sorts[sortIndex];
        const icon = document.createElement('i');
        icon.className = `bi ${sort.direction === 'asc' ? 'bi-arrow-up' : 'bi-arrow-down'}`;
        const badge = document.createElement('span');
        badge.className = 'db-sort-order';
        badge.textContent = sortIndex + 1;
        button.append(icon, badge);
      }
      button.addEventListener('click', () => cycleSort(column.name));
      th.appendChild(button);
      row.appendChild(th);
    }
    els.head.replaceChildren(row);
  }

  function renderBody() {
    if (!state.table) {
      els.body.innerHTML = '<tr><td class="text-secondary p-4">Select a table to view rows.</td></tr>';
      return;
    }
    if (state.rows.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = Math.max(state.columns.length, 1);
      td.className = 'text-secondary p-4';
      td.textContent = 'No rows match the current view.';
      tr.appendChild(td);
      els.body.replaceChildren(tr);
      return;
    }

    const rows = state.rows.map((row) => {
      const tr = document.createElement('tr');
      const pk = pkForRow(row);
      for (const column of state.columns) {
        const td = document.createElement('td');
        const key = cellKey(pk, column.name);
        const pending = state.pending.get(key);
        td.tabIndex = column.primary_key ? -1 : 0;
        td.dataset.key = key;
        td.dataset.column = column.name;
        td.dataset.pk = JSON.stringify(pk);
        td.className = column.primary_key ? 'db-primary-key' : 'db-editable-cell';
        if (state.selected.has(key)) td.classList.add('db-cell-selected');
        if (pending) td.classList.add('db-cell-pending');
        td.textContent = displayValue(pending ? pending.value : row[column.name]);
        if (!column.primary_key) {
          td.addEventListener('mousedown', (event) => startCellDrag(event, td));
          td.addEventListener('mouseenter', () => continueCellDrag(td));
          td.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              toggleCell(td);
            }
          });
        }
        tr.appendChild(td);
      }
      return tr;
    });
    els.body.replaceChildren(...rows);
  }

  function renderMeta() {
    els.title.textContent = state.table || 'DB';
    const start = state.total === 0 ? 0 : ((state.page - 1) * state.perPage) + 1;
    const end = Math.min(state.page * state.perPage, state.total);
    els.meta.textContent = state.table
      ? `${state.columns.length} fields, ${state.total} rows`
      : 'Select a table';
    els.pageSummary.textContent = state.table
      ? `Rows ${start}-${end} of ${state.total} | Page ${state.page} of ${state.pages}`
      : '';
    els.prev.disabled = !state.table || state.page <= 1;
    els.next.disabled = !state.table || state.page >= state.pages;
  }

  function renderAll() {
    renderTableList();
    renderHeader();
    renderBody();
    renderMeta();
    updateBadges();
  }

  async function loadTables() {
    setBusy(true);
    try {
      const response = await fetch('/api/db/tables');
      if (!response.ok) throw new Error('Could not load tables');
      state.tables = await response.json();
      renderTableList();
      if (state.tables.length) {
        await selectTable(state.tables[0].name);
      }
    } catch (error) {
      showAlert(error.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  async function selectTable(tableName) {
    state.table = tableName;
    state.page = 1;
    state.sorts = [];
    state.selected.clear();
    state.selectedColumn = null;
    state.pending.clear();
    await loadRows();
  }

  async function loadRows() {
    if (!state.table) return;
    setBusy(true);
    const params = new URLSearchParams({
      page: state.page,
      per_page: state.perPage,
    });
    if (els.filter.value.trim()) params.set('filter', els.filter.value.trim());
    if (sortQuery()) params.set('sort', sortQuery());
    try {
      const response = await fetch(`/api/db/tables/${encodeURIComponent(state.table)}?${params}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not load rows');
      state.columns = data.columns;
      state.primaryKey = data.primary_key;
      state.rows = data.rows;
      state.page = data.page;
      state.pages = data.pages;
      state.total = data.total;
      state.selected.clear();
      state.selectedColumn = null;
      renderAll();
    } catch (error) {
      showAlert(error.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  function cycleSort(column) {
    const index = state.sorts.findIndex((sort) => sort.column === column);
    if (index === -1) {
      state.sorts.push({ column, direction: 'asc' });
    } else if (state.sorts[index].direction === 'asc') {
      state.sorts[index].direction = 'desc';
    } else {
      state.sorts.splice(index, 1);
    }
    state.page = 1;
    loadRows();
  }

  function toggleCell(cell) {
    const key = cell.dataset.key;
    const shouldSelect = !state.selected.has(key);
    if (selectCell(cell, shouldSelect) && shouldSelect) {
      loadEditorFromCell(cell);
    }
  }

  function startCellDrag(event, cell) {
    if (event.button !== 0) return;
    event.preventDefault();
    const key = cell.dataset.key;
    const shouldSelect = !state.selected.has(key);
    const selected = selectCell(cell, shouldSelect);
    if (!selected || !shouldSelect) return;
    loadEditorFromCell(cell);
    state.isDragging = true;
    state.dragColumn = cell.dataset.column;
  }

  function continueCellDrag(cell) {
    if (!state.isDragging || cell.dataset.column !== state.dragColumn) return;
    selectCell(cell, true);
  }

  function applyBulkValue() {
    if (state.selected.size === 0) {
      showAlert('Select one or more editable fields first.', 'warning');
      return;
    }
    for (const key of state.selected) {
      const cell = Array.from(els.body.querySelectorAll('[data-key]'))
        .find((candidate) => candidate.dataset.key === key);
      if (!cell) continue;
      const value = els.bulkValue.value;
      state.pending.set(key, {
        pk: JSON.parse(cell.dataset.pk),
        column: cell.dataset.column,
        value,
      });
      cell.textContent = value;
      cell.classList.add('db-cell-pending');
    }
    updateBadges();
  }

  async function commitChanges() {
    if (state.pending.size === 0) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/db/tables/${encodeURIComponent(state.table)}/updates`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates: Array.from(state.pending.values()) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not commit updates');
      showAlert(data.message || 'Updates committed', 'success');
      state.pending.clear();
      state.selected.clear();
      state.selectedColumn = null;
      await loadRows();
    } catch (error) {
      showAlert(error.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  function cancelChanges() {
    state.pending.clear();
    state.selected.clear();
    state.selectedColumn = null;
    renderAll();
  }

  document.addEventListener('mouseup', () => {
    state.isDragging = false;
    state.dragColumn = null;
  });

  let filterTimer = null;
  els.filter.addEventListener('input', () => {
    window.clearTimeout(filterTimer);
    filterTimer = window.setTimeout(() => {
      state.page = 1;
      loadRows();
    }, 350);
  });
  els.clearFilter.addEventListener('click', () => {
    els.filter.value = '';
    state.page = 1;
    loadRows();
  });
  els.applyBulk.addEventListener('click', applyBulkValue);
  els.commit.addEventListener('click', commitChanges);
  els.cancel.addEventListener('click', cancelChanges);
  els.prev.addEventListener('click', () => {
    if (state.page > 1) {
      state.page -= 1;
      loadRows();
    }
  });
  els.next.addEventListener('click', () => {
    if (state.page < state.pages) {
      state.page += 1;
      loadRows();
    }
  });
  els.pageSize.addEventListener('change', () => {
    state.perPage = Number.parseInt(els.pageSize.value, 10);
    state.page = 1;
    loadRows();
  });

  loadTables();
});
