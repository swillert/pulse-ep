/* ─── toast helper ──────────────────────────────────── */
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

export default class DataManagementController {
  constructor() {
    this.metadata    = {};
    this.filters     = {};
    this.allEPMaps   = [];
    this.selectedIds = new Set();
  }

  initialize() {
    this._bindControls();
    this.fetchAvailableAttributes()
      .then(() => { this.populateFilters(); this.fetchData(); });
    this.loadGroups();
  }

  /* ── Bind UI controls ─────────────────────────────── */
  _bindControls() {
    document.getElementById('filterButton')
      ?.addEventListener('click', () => this.applyFilters());
    document.getElementById('clearFiltersButton')
      ?.addEventListener('click', () => this._clearFilters());

    document.getElementById('closeModal')
      ?.addEventListener('click', () => this._closeModal('addAttributeModal'));
    document.getElementById('cancelAttrModal')
      ?.addEventListener('click', () => this._closeModal('addAttributeModal'));
    document.getElementById('saveAttributeButton')
      ?.addEventListener('click', () => this.addAttribute());
    document.getElementById('addAttributeBtn')
      ?.addEventListener('click', () => this._openModal('addAttributeModal'));

    document.getElementById('saveGroupButton')
      ?.addEventListener('click', () => this._openSaveGroupDialog());
    document.getElementById('closeSaveGroupModal')
      ?.addEventListener('click', () => this._closeModal('saveGroupModal'));
    document.getElementById('cancelSaveGroup')
      ?.addEventListener('click', () => this._closeModal('saveGroupModal'));
    document.getElementById('confirmSaveGroup')
      ?.addEventListener('click', () => this._saveGroup());

    document.getElementById('refreshGroupsBtn')
      ?.addEventListener('click', () => this.loadGroups());

    document.querySelectorAll('.modal-overlay').forEach(m => {
      m.addEventListener('click', e => { if (e.target === m) m.classList.remove('open'); });
    });
  }

  /* ── Attribute metadata ───────────────────────────── */
  async fetchAvailableAttributes() {
    try {
      const res = await this._api('GET', '/epmaps/distinct_attributes');
      if (!res.ok) return;
      const { distinct_attributes } = await res.json();
      distinct_attributes.forEach(a => {
        this.metadata[a.name] = { type: a.type, defaultValue: a.default_value ?? '' };
      });
    } catch (e) { console.error('fetchAvailableAttributes', e); }
  }

  populateFilters() {
    const container = document.getElementById('attributeFilters');
    container.innerHTML = '';
    Object.entries(this.metadata).forEach(([name, meta]) => {
      const wrap  = document.createElement('div');
      wrap.className = 'filter-item';
      const label = document.createElement('label');
      label.textContent = name;
      wrap.appendChild(label);
      wrap.appendChild(meta.type === 'boolean'
        ? this._mkSelect(name, ['', 'true', 'false'], ['All', 'True', 'False'])
        : this._mkInput(name, meta.type === 'number' ? 'number' : 'text'));
      container.appendChild(wrap);
    });
  }

  _mkSelect(name, values, labels) {
    const s = document.createElement('select'); s.name = name;
    values.forEach((v, i) => {
      const o = document.createElement('option');
      o.value = v; o.textContent = labels[i]; s.appendChild(o);
    });
    return s;
  }
  _mkInput(name, type) {
    const i = document.createElement('input'); i.name = name; i.type = type; return i;
  }

  applyFilters() {
    const filters = {};
    document.querySelectorAll('#attributeFilters select, #attributeFilters input')
      .forEach(el => { if (el.value) filters[el.name] = el.value; });
    this.filters = filters;
    this.fetchData(filters);
  }

  _clearFilters() {
    document.querySelectorAll('#attributeFilters select, #attributeFilters input')
      .forEach(el => { el.value = ''; });
    this.filters = {};
    this.fetchData();
  }

  /* ── Fetch data ───────────────────────────────────── */
  async fetchData(filters = {}) {
    try {
      const r1 = await this._api('POST', '/epmaps/filter_by_attributes', { filters });
      if (!r1.ok) { toast('Failed to load maps', 'error'); return; }
      const { map_ids } = await r1.json();
      if (!map_ids.length) { this.allEPMaps = []; this._renderTable([], []); return; }

      const r2 = await this._api('POST', '/get_epmaps', { epmap_ids: map_ids });
      if (!r2.ok) { toast('Failed to load map details', 'error'); return; }
      const epMaps = await r2.json();
      await this._fetchAndRenderWithAttributes(epMaps);
    } catch (e) { console.error('fetchData', e); toast('Error loading data', 'error'); }
  }

  async _fetchAndRenderWithAttributes(epMaps) {
    try {
      const ids = epMaps.map(m => m.id);
      const r = await this._api('POST', '/epmaps/get_attributes', { map_ids: ids, attributes: [] });
      const attrsData = r.ok ? (await r.json()).attributes : {};
      const allAttrs = new Set();
      epMaps.forEach(m => {
        m.attributes = attrsData[m.id] || {};
        Object.keys(m.attributes).forEach(k => allAttrs.add(k));
      });
      this.allEPMaps = epMaps;
      this._renderTable(epMaps, Array.from(allAttrs));
    } catch (e) { console.error('_fetchAndRenderWithAttributes', e); }
  }

  /* ── Table rendering ──────────────────────────────── */
  _renderTable(maps, attrs) {
    const table = document.getElementById('epmapsTable');
    const thead = table.querySelector('thead tr');
    const tbody = table.querySelector('tbody');
    document.getElementById('totalCount').textContent = maps.length;

    /* header */
    thead.innerHTML = `
      <th class="check-col"><input type="checkbox" id="selectAll" title="Select all"></th>
      <th class="id-col">ID</th>
      <th>Study</th><th>Map Name</th><th>Points</th>`;
    attrs.forEach(a => {
      const th = document.createElement('th'); th.textContent = a; thead.appendChild(th);
    });
    const addTh = document.createElement('th');
    addTh.innerHTML = '<i class="fas fa-plus" title="Add attribute" style="color:var(--accent)"></i>';
    addTh.style.cssText = 'width:36px;text-align:center;cursor:pointer';
    addTh.addEventListener('click', () => this._openModal('addAttributeModal'));
    thead.appendChild(addTh);

    document.getElementById('selectAll').addEventListener('change', e => {
      this._setAllSelected(e.target.checked);
    });

    /* rows */
    tbody.innerHTML = '';
    if (!maps.length) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td colspan="${5 + attrs.length + 1}" style="text-align:center;
        color:var(--text-3);padding:32px 16px">No maps match the current filters.</td>`;
      tbody.appendChild(tr); return;
    }

    maps.forEach(m => {
      const tr = document.createElement('tr');
      if (this.selectedIds.has(m.id)) tr.classList.add('selected');

      const chk = document.createElement('input');
      chk.type = 'checkbox'; chk.className = 'row-check';
      chk.checked = this.selectedIds.has(m.id);
      chk.addEventListener('change', () => this._toggleSelect(m.id, chk.checked, tr));

      const tdChk = document.createElement('td'); tdChk.className = 'check-col';
      tdChk.appendChild(chk);
      tr.appendChild(tdChk);

      tr.insertAdjacentHTML('beforeend', `
        <td class="id-col">${m.id}</td>
        <td>${m.study_name}</td>
        <td>${m.map_name}</td>
        <td>${m.number_of_points ?? '—'}</td>`);

      attrs.forEach(attr => {
        const td   = document.createElement('td');
        const meta = this.metadata[attr] || { type: 'string' };
        const val  = m.attributes[attr];

        if (meta.type === 'boolean') {
          const sel = this._mkSelect(attr, ['', 'true', 'false'], ['—', 'True', 'False']);
          sel.value = val === true ? 'true' : val === false ? 'false' : '';
          sel.addEventListener('change', () => {
            const v = sel.value === 'true' ? true : sel.value === 'false' ? false : null;
            this.updateAttribute(m.id, attr, v);
          });
          td.appendChild(sel);
        } else if (meta.type === 'number') {
          const inp = document.createElement('input'); inp.type = 'number';
          inp.value = val ?? meta.defaultValue ?? '';
          inp.addEventListener('blur', () => this.updateAttribute(m.id, attr, parseFloat(inp.value)));
          td.appendChild(inp);
        } else {
          td.contentEditable = 'true';
          td.textContent = val ?? '';
          td.addEventListener('blur', () => this.updateAttribute(m.id, attr, td.textContent.trim()));
        }
        tr.appendChild(td);
      });

      tr.appendChild(document.createElement('td'));
      tbody.appendChild(tr);
    });

    this._updateSelectionUI();
  }

  /* ── Selection ────────────────────────────────────── */
  _toggleSelect(id, checked, row) {
    checked ? this.selectedIds.add(id) : this.selectedIds.delete(id);
    row.classList.toggle('selected', checked);
    this._updateSelectionUI();
  }

  _setAllSelected(checked) {
    this.selectedIds.clear();
    document.querySelectorAll('.row-check').forEach((chk, i) => {
      chk.checked = checked;
      chk.closest('tr').classList.toggle('selected', checked);
      if (checked && this.allEPMaps[i]) this.selectedIds.add(this.allEPMaps[i].id);
    });
    this._updateSelectionUI();
  }

  _updateSelectionUI() {
    const n    = this.selectedIds.size;
    const info = document.getElementById('selectionInfo');
    const btn  = document.getElementById('saveGroupButton');
    document.getElementById('selectionCount').textContent = n;
    info?.classList.toggle('hidden', n === 0);
    if (btn) btn.disabled = n === 0;
  }

  /* ── Add Attribute ────────────────────────────────── */
  async addAttribute() {
    const name = document.getElementById('attributeName').value.trim();
    const type = document.getElementById('attributeType').value;
    let   def  = document.getElementById('attributeDefault').value;
    if (!name) { toast('Please enter an attribute name', 'error'); return; }

    if (type === 'boolean') def = def.toLowerCase() === 'true';
    else if (type === 'number') def = def ? parseFloat(def) : null;
    else if (!def) def = null;

    const ids = this.allEPMaps.map(m => m.id);
    if (!ids.length) { toast('No maps loaded', 'error'); return; }

    const r = await this._api('POST', '/epmaps/set_attributes',
      { map_ids: ids, attribute_values: { [name]: def } });
    if (r.ok) {
      toast(`Attribute "${name}" added`, 'success');
      this._closeModal('addAttributeModal');
      document.getElementById('attributeName').value  = '';
      document.getElementById('attributeDefault').value = '';
      await this.fetchAvailableAttributes();
      this.populateFilters();
      this.fetchData(this.filters);
    } else {
      toast('Failed to add attribute', 'error');
    }
  }

  /* ── Update cell ──────────────────────────────────── */
  async updateAttribute(mapId, attrName, value) {
    const parsed = typeof value === 'boolean' ? value
      : (value !== null && !isNaN(value) && value !== '') ? parseFloat(value)
      : String(value).trim();
    const r = await this._api('POST', '/epmaps/set_attributes',
      { map_ids: [mapId], attribute_values: { [attrName]: parsed } });
    if (!r.ok) toast('Failed to save attribute', 'error');
  }

  /* ── Save Group ───────────────────────────────────── */
  async _openSaveGroupDialog() {
    if (!this.selectedIds.size) return;
    const sel = document.getElementById('groupColormap');
    sel.innerHTML = '<option value="">— none —</option>';
    try {
      const r = await this._api('GET', '/colormaps');
      if (r.ok) {
        const cms = await r.json();
        cms.forEach(c => {
          const o = document.createElement('option');
          o.value = c.id; o.textContent = c.name; sel.appendChild(o);
        });
      }
    } catch (_) {}

    const n = this.selectedIds.size;
    document.getElementById('saveGroupSummaryText').textContent =
      `${n} map${n !== 1 ? 's' : ''} will be added to this group.`;
    document.getElementById('groupName').value = '';
    this._openModal('saveGroupModal');
  }

  async _saveGroup() {
    const name     = document.getElementById('groupName').value.trim();
    const cmSel    = document.getElementById('groupColormap');
    const cmId     = cmSel.value || null;
    const cmName   = cmId ? cmSel.options[cmSel.selectedIndex].text : null;
    const datatype = document.getElementById('groupDatatype')?.value || 'act';
    const distance = parseFloat(document.getElementById('groupDistance')?.value || '5') || 5;
    const mapIds   = Array.from(this.selectedIds);

    if (!name) { toast('Please enter a group name', 'error'); return; }

    const btn = document.getElementById('confirmSaveGroup');
    btn.disabled = true; btn.textContent = 'Saving…';

    const r = await this._api('POST', '/save_report', {
      report_name:   name,
      colormap_id:   cmId,
      colormap_name: cmName,
      datatype,
      distance,
      map_ids:       mapIds,
      additional_data: {}
    });

    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-check"></i> Save Group';

    if (r.ok) {
      toast(`Group "${name}" saved (${mapIds.length} maps)`, 'success');
      this._closeModal('saveGroupModal');
      this.selectedIds.clear();
      this._setAllSelected(false);
      this.loadGroups();
    } else {
      toast('Failed to save group', 'error');
    }
  }

  /* ── Groups list ──────────────────────────────────── */
  async loadGroups() {
    const list = document.getElementById('groupsList');
    if (!list) return;
    list.innerHTML = `<div style="text-align:center;padding:24px">
      <span class="spinner"></span></div>`;
    try {
      const r = await this._api('GET', '/reports');
      if (!r.ok) throw new Error();
      const groups = await r.json();
      const countEl = document.getElementById('groupCount');
      if (countEl) countEl.textContent = groups.length;
      this._renderGroups(groups, list);
    } catch (_) {
      list.innerHTML = `<div class="groups-empty" style="color:var(--danger)">
        <i class="fas fa-exclamation-triangle"></i><p>Failed to load groups</p></div>`;
    }
  }

  _renderGroups(groups, list) {
    list.innerHTML = '';
    if (!groups.length) {
      list.innerHTML = `<div class="groups-empty">
        <i class="fas fa-layer-group"></i>
        <p>No groups yet</p>
        <small>Select maps and click "Save as Group"</small>
      </div>`; return;
    }
    groups.forEach(g => {
      const card    = document.createElement('div');
      card.className = 'group-card';
      const n       = g.map_ids?.length ?? 0;
      const cm      = g.colormap_name || '—';
      const hasFile = !!g.additional_data?.excel_file;
      card.innerHTML = `
        <div class="group-card-header">
          <div class="group-card-name">${g.report_name}</div>
          <div class="group-card-actions">
            ${hasFile ? `<button class="btn-icon dl" title="Download Excel"><i class="fas fa-download"></i></button>` : ''}
            <button class="btn-icon run" title="${hasFile ? 'Re-generate' : 'Generate report'}"><i class="fas fa-${hasFile ? 'redo' : 'play'}"></i></button>
            <button class="btn-icon del" title="Delete"><i class="fas fa-trash"></i></button>
          </div>
        </div>
        <div class="group-card-meta">
          <span><i class="fas fa-map-marker-alt"></i> ${n} map${n !== 1 ? 's' : ''}</span>
          <span><i class="fas fa-palette"></i> ${cm}</span>
        </div>`;
      const runBtn = card.querySelector('.run');
      runBtn.addEventListener('click', () => this._runGroup(g.id, g.report_name, runBtn));
      card.querySelector('.del').addEventListener('click', () => this._deleteGroup(g.id, card));
      card.querySelector('.dl')?.addEventListener('click', () => this._downloadGroup(g.id, g.report_name));
      list.appendChild(card);
    });
  }

  async _runGroup(id, name, btn) {
    const token = localStorage.getItem('token');
    const resp  = await fetch(`/reports/${id}/generate`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      toast(err.error || 'Failed to start report', 'error');
      return;
    }
    toast(`"${name}" generation started`, 'info');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }
    // Poll until done, then refresh the groups panel
    const poller = setInterval(async () => {
      try {
        const r    = await fetch(`/reports/${id}/status`, { headers: { 'Authorization': `Bearer ${token}` } });
        const data = await r.json();
        if (data.status === 'ready' || data.status === 'error') {
          clearInterval(poller);
          this.loadGroups();
        }
      } catch (_) {}
    }, 3000);
  }

  async _downloadGroup(id, name) {
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

  async _deleteGroup(id, card) {
    if (!confirm('Delete this group? This cannot be undone.')) return;
    const r = await this._api('DELETE', `/reports/${id}`);
    if (r.ok) {
      card.style.transition = 'opacity .2s'; card.style.opacity = '0';
      setTimeout(() => { card.remove(); this.loadGroups(); }, 200);
      toast('Group deleted', 'success');
    } else {
      toast('Failed to delete group', 'error');
    }
  }

  /* ── Helpers ──────────────────────────────────────── */
  _openModal(id)  { document.getElementById(id)?.classList.add('open'); }
  _closeModal(id) { document.getElementById(id)?.classList.remove('open'); }

  _api(method, url, body) {
    const token = localStorage.getItem('token');
    const opts  = { method, headers: { 'Authorization': `Bearer ${token}`,
                                       'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    return fetch(url, opts);
  }
}
