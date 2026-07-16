/**
 * BB Study – shared utilities loaded on every page.
 */

/* ── Theme toggle (navbar button) ─────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('themeToggleBtn');
  if (btn) {
    btn.addEventListener('click', () => {
      const html = document.documentElement;
      const current = html.getAttribute('data-bs-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      // Update DOM immediately for instant feedback
      html.setAttribute('data-bs-theme', next);
      btn.querySelector('i').className = next === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
      // Persist to DB
      fetch('/api/settings/theme', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: next }),
      });
    });
  }

  const gitPublishBtn = document.getElementById('gitPublishBtn');
  if (gitPublishBtn) {
    gitPublishBtn.addEventListener('click', async () => {
      if (!window.confirm('Commit all repository changes and push them to origin?')) return;

      const label = gitPublishBtn.querySelector('span');
      const originalLabel = label.textContent;
      gitPublishBtn.disabled = true;
      label.textContent = 'Publishing…';

      try {
        const response = await fetch('/api/git/publish', { method: 'POST' });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Commit and push failed.');
        showAlert(payload.message, 'success', 6000);
      } catch (error) {
        showAlert(error.message, 'danger', 8000);
      } finally {
        gitPublishBtn.disabled = false;
        label.textContent = originalLabel;
      }
    });
  }
});

/* ── Alert helper ──────────────────────────────────────────────────────────── */
function showAlert(message, type = 'info', duration = 4000) {
  const container = document.getElementById('alertContainer');
  if (!container) return;
  const div = document.createElement('div');
  div.className = `alert alert-${type} alert-dismissible fade show`;
  // Build DOM nodes to avoid innerHTML with untrusted content
  const msgNode = document.createTextNode(message);
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn-close';
  btn.setAttribute('data-bs-dismiss', 'alert');
  div.appendChild(msgNode);
  div.appendChild(btn);
  container.appendChild(div);
  if (duration > 0) {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(div);
      bsAlert.close();
    }, duration);
  }
}
