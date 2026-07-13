/* Import-queue review UI — lists jobs, shows/edits a job's plan, approves. */
(() => {
  const API = '/api/import-jobs';
  const token = () => localStorage.getItem('token');
  const headers = (json) => ({
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    Authorization: `Bearer ${token()}`,
  });

  const listEl = document.getElementById('jobList');
  const detailEl = document.getElementById('detail');
  let selectedId = null;

  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const base = (p) => String(p || '').split('/').filter(Boolean).pop() || p;
  const mb = (b) => `${((b || 0) / 1e6).toFixed(1)} MB`;

  async function api(path, opts = {}) {
    const r = await fetch(API + path, { ...opts, headers: headers(opts.body != null) });
    if (r.status === 401) { location.href = '/login'; return null; }
    return r;
  }

  async function loadJobs() {
    const r = await api('');
    if (!r) return;
    const jobs = await r.json();
    listEl.innerHTML = jobs.length
      ? jobs.map((j) => `
        <div class="job ${j.id === selectedId ? 'sel' : ''}" data-id="${j.id}">
          <div class="path">${esc(base(j.source_path))}</div>
          <div class="meta">${esc(j.vendor || '—')} ·
            <span class="badge ${j.status}">${esc(j.status)}</span></div>
        </div>`).join('')
      : '<div class="empty">No jobs. Scan the drop directory.</div>';
    listEl.querySelectorAll('.job').forEach((el) =>
      el.addEventListener('click', () => selectJob(Number(el.dataset.id))));
  }

  async function selectJob(id) {
    selectedId = id;
    await loadJobs();
    const r = await api(`/${id}`);
    if (!r) return;
    renderDetail(await r.json());
  }

  function renderDetail(job) {
    if (job.status === 'error') {
      detailEl.innerHTML = `<h2>Job ${job.id}</h2>
        <div class="sub">${esc(job.source_path)}</div>
        <div class="err">${esc(job.error || 'error')}</div>`;
      return;
    }
    if (job.status === 'done') {
      detailEl.innerHTML = `<h2>Imported ✓</h2>
        <div class="sub">${esc(job.source_path)}</div>
        <div class="section">Study id <b>${job.study_id}</b> persisted.</div>`;
      return;
    }
    if (job.status === 'detected' || !job.plan) {
      detailEl.innerHTML = `<h2>${esc(base(job.source_path))}</h2>
        <div class="sub">${esc(job.vendor || 'unknown vendor')} · detected</div>
        <div class="actions"><button class="primary" id="prepBtn">Prepare (dry-run)</button></div>`;
      document.getElementById('prepBtn').onclick = async () => {
        await api(`/${job.id}/prepare`, { method: 'POST', body: '{}' });
        selectJob(job.id);
      };
      return;
    }

    // needs_review / importing → show the editable plan
    const plan = job.plan;
    const sp = (plan.studies || [])[0] || {};
    const maps = sp.maps || [];
    const wf = sp.waveforms || {};
    const busy = job.status === 'importing';

    detailEl.innerHTML = `
      <h2>${esc(sp.study_name || base(job.source_path))}</h2>
      <div class="sub">${esc(sp.vendor || '')} · ${esc((sp.provenance || {}).software_version || '')}</div>

      <div class="section"><h3>Maps (${maps.length})</h3>
        <table><thead><tr><th>Import</th><th>Name</th><th>Part</th><th>Verts</th><th>Fields</th><th>Points</th></tr></thead>
        <tbody>${maps.map((m, i) => `
          <tr>
            <td><input type="checkbox" data-map="${i}" data-k="include" ${m.include ? 'checked' : ''}></td>
            <td>${esc(m.map_name)}</td><td>${esc(m.part || '')}</td>
            <td>${m.n_vertices ?? ''}</td><td>${esc((Object.keys(m.scalar_fields || {})).join(', '))}</td>
            <td><input type="checkbox" data-map="${i}" data-k="include_points" ${m.include_points ? 'checked' : ''}
                 ${(m.points_files || []).length ? '' : 'disabled'}></td>
          </tr>`).join('')}</tbody></table>
      </div>

      <div class="section"><h3>Other data</h3>
        <label class="chk"><input type="checkbox" id="wfInc" ${wf.include ? 'checked' : ''}
          ${(wf.files || []).length ? '' : 'disabled'}>
          Waveforms — ${(wf.files || []).length} files, ~${mb(wf.estimated_bytes)} <em>(opt-in)</em></label><br>
        <label class="chk"><input type="checkbox" id="ppInc" ${sp.include_placed_points ? 'checked' : ''}
          ${(sp.placed_point_files || []).length ? '' : 'disabled'}>
          Placed points — ${(sp.placed_point_files || []).length} files</label><br>
        <label class="chk"><input type="checkbox" id="anInc" ${sp.include_anatomy ? 'checked' : ''}
          ${(sp.anatomy_files || []).length ? '' : 'disabled'}>
          Anatomy (Model Groups) — ${(sp.anatomy_files || []).length} files</label>
      </div>

      <div class="actions">
        <button class="primary" id="importBtn" ${busy ? 'disabled' : ''}>${busy ? 'Importing…' : 'Import study'}</button>
      </div>`;

    // bind edits back into the plan object
    detailEl.querySelectorAll('input[data-map]').forEach((el) =>
      el.addEventListener('change', () => { maps[+el.dataset.map][el.dataset.k] = el.checked; }));
    const bind = (id, set) => { const e = document.getElementById(id); if (e) e.addEventListener('change', () => set(e.checked)); };
    bind('wfInc', (v) => { wf.include = v; });
    bind('ppInc', (v) => { sp.include_placed_points = v; });
    bind('anInc', (v) => { sp.include_anatomy = v; });

    const btn = document.getElementById('importBtn');
    if (btn) btn.onclick = async () => {
      btn.disabled = true; btn.textContent = 'Importing…';
      await api(`/${job.id}/plan`, { method: 'PATCH', body: JSON.stringify(plan) });
      await api(`/${job.id}/commit`, { method: 'POST', body: '{}' });
      selectJob(job.id);
    };
  }

  document.getElementById('refreshBtn').onclick = loadJobs;
  document.getElementById('scanBtn').onclick = async () => {
    await api('/scan', { method: 'POST', body: '{}' });
    loadJobs();
  };

  loadJobs();
})();
