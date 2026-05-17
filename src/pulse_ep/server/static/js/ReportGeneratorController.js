function toast(msg, type = 'info', duration = 3000) {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  const icon = { success: 'check-circle', error: 'exclamation-circle', info: 'info-circle' }[type] || 'info-circle';
  t.innerHTML = `<i class="fas fa-${icon}"></i> ${msg}`;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s';
                     setTimeout(() => t.remove(), 300); }, duration);
}

export default class ReportGeneratorController {
  constructor() {
    this.reports  = [];
    this._pollers = {}; // report_id → interval handle
    document.getElementById('refreshReportsButton')
      ?.addEventListener('click', () => this.fetchReports());
    this.fetchReports();
  }

  async fetchReports() {
    const container = document.getElementById('reportsContainer');
    container.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px">
      <span class="spinner"></span></div>`;

    try {
      const token = localStorage.getItem('token');
      const r = await fetch('/reports', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!r.ok) throw new Error(r.statusText);
      this.reports = await r.json();
      document.getElementById('reportCount').textContent = this.reports.length;
      this._renderCards(this.reports);
    } catch (e) {
      console.error('fetchReports', e);
      container.innerHTML = `<div class="rg-empty">
        <i class="fas fa-exclamation-triangle"></i>
        <p>Failed to load reports</p>
        <small>${e.message}</small>
      </div>`;
    }
  }

  _renderCards(reports) {
    const container = document.getElementById('reportsContainer');
    container.innerHTML = '';

    if (!reports.length) {
      container.innerHTML = `<div class="rg-empty">
        <i class="fas fa-file-alt"></i>
        <p>No reports yet</p>
        <small>Create groups in the Data Manager, then run them here.</small>
      </div>`;
      return;
    }

    reports.forEach(r => {
      const card = this._makeCard(r);
      container.appendChild(card);

      // If this report is currently generating, start polling
      if (r.additional_data?.status === 'generating') {
        this._startPolling(r.id, card);
      }
    });
  }

  _makeCard(r) {
    const card     = document.createElement('div');
    card.className = 'report-card';
    card.dataset.id = r.id;

    const n        = r.map_ids?.length ?? 0;
    const cm       = r.colormap_name || '—';
    const datatype = r.additional_data?.datatype || 'act';
    const distance = r.additional_data?.distance ?? 5;
    const status   = r.additional_data?.status;   // generating | ready | error | undefined
    const hasFile  = status === 'ready' && !!r.additional_data?.excel_file;

    const statusBadge = status === 'generating'
      ? `<span class="badge generating"><span class="spinner" style="width:10px;height:10px;border-width:2px"></span> Generating…</span>`
      : status === 'ready'
        ? `<span class="badge ready"><i class="fas fa-check"></i> Ready</span>`
        : status === 'error'
          ? `<span class="badge error" title="${r.additional_data?.error || ''}"><i class="fas fa-exclamation-triangle"></i> Error</span>`
          : '';

    card.innerHTML = `
      <div class="report-card-top">
        <div>
          <div class="report-card-title">${r.report_name}</div>
          <div class="report-card-id"># ${r.id}</div>
        </div>
        ${statusBadge}
      </div>
      <div class="report-card-body">
        <div class="row"><i class="fas fa-map-marker-alt"></i><span>${n} map${n !== 1 ? 's' : ''}</span></div>
        <div class="row"><i class="fas fa-palette"></i><span>${cm}</span></div>
        <div class="row"><i class="fas fa-wave-square"></i><span>${datatype.toUpperCase()} · ${distance} mm</span></div>
      </div>
      <div class="report-card-footer">
        <button class="btn-run" ${status === 'generating' ? 'disabled' : ''}>
          <i class="fas fa-${hasFile ? 'redo' : 'play'}"></i> ${hasFile ? 'Re-generate' : 'Generate'}
        </button>
        <div class="spacer"></div>
        ${hasFile ? `<button class="btn-dl" title="Download Excel"><i class="fas fa-download"></i></button>` : ''}
        <button class="btn-del"><i class="fas fa-trash"></i></button>
      </div>`;

    card.querySelector('.btn-run').addEventListener('click', () => this._generate(r.id, r.report_name, card));
    card.querySelector('.btn-del').addEventListener('click', () => this._delete(r.id, card));
    card.querySelector('.btn-dl')?.addEventListener('click', () => this._download(r.id, r.report_name));
    return card;
  }

  async _generate(id, name, card) {
    const token = localStorage.getItem('token');
    const r = await fetch(`/reports/${id}/generate`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      toast(err.error || 'Failed to start', 'error');
      return;
    }
    toast(`"${name}" generation started`, 'info');
    // Update card to show generating state and start polling
    const top = card.querySelector('.report-card-top');
    // Remove old badge if any
    top.querySelector('.badge')?.remove();
    top.insertAdjacentHTML('beforeend',
      `<span class="badge generating"><span class="spinner" style="width:10px;height:10px;border-width:2px"></span> Generating…</span>`);
    card.querySelector('.btn-run').disabled = true;
    this._startPolling(id, card);
  }

  _startPolling(id, card) {
    if (this._pollers[id]) return; // already polling
    this._pollers[id] = setInterval(async () => {
      const token = localStorage.getItem('token');
      try {
        const r    = await fetch(`/reports/${id}/status`, { headers: { 'Authorization': `Bearer ${token}` } });
        const data = await r.json();
        if (data.status === 'ready' || data.status === 'error') {
          clearInterval(this._pollers[id]);
          delete this._pollers[id];
          this.fetchReports(); // reload all cards
        }
      } catch (_) {}
    }, 3000);
  }

  async _download(id, name) {
    const token = localStorage.getItem('token');
    const r     = await fetch(`/reports/${id}/download`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      toast(err.error || 'Download failed', 'error');
      return;
    }
    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = name.replace(/\s+/g, '_') + '.xlsx';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async _delete(id, card) {
    if (!confirm('Delete this report? This cannot be undone.')) return;
    const btn = card.querySelector('.btn-del');
    btn.disabled = true;

    try {
      const token = localStorage.getItem('token');
      const r = await fetch(`/reports/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (r.ok) {
        clearInterval(this._pollers[id]);
        delete this._pollers[id];
        card.style.transition = 'opacity .2s, transform .2s';
        card.style.opacity = '0';
        card.style.transform = 'scale(.96)';
        setTimeout(() => { card.remove(); this.fetchReports(); }, 200);
        toast('Report deleted', 'success');
      } else {
        throw new Error(await r.text());
      }
    } catch (e) {
      toast(`Failed to delete: ${e.message}`, 'error');
      btn.disabled = false;
    }
  }
}
