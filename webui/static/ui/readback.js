"use strict";

// Structured protocol-readback diagnostics.

// ---- profile-driven nested protocol readbacks -----------------------
const RB_ESC = {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'};
const rbEscape = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => RB_ESC[c]);
const rbHex = value => '0x' + Number(value || 0).toString(16).padStart(2, '0');
const rbNum = value => Number.isFinite(Number(value)) ? String(Number(value)) : '–';

function rbCurrentEntries(layout) {
  return Object.entries(layout.current || {}).sort((a, b) => Number(a[0]) - Number(b[0]));
}

function rbLayoutBound(layout) {
  if (layout.index != null) return `index ${layout.index}`;
  if (Array.isArray(layout.index_range)) return `indices ${layout.index_range[0]}–${layout.index_range[1]}`;
  return 'outer index unknown';
}

function rbLinkBody(layout, entries) {
  const bits = entries.flatMap(([outer, records]) => records.map(record => {
    const on = Number(record.linked) !== 0;
    const title = `${layout.name} entry ${record.record_index}: raw ${record.raw || '–'}`;
    return `<span class="rbbit${on ? ' on' : ''}" title="${rbEscape(title)}">`
      + `${rbEscape(outer)}:${record.record_index} ${on ? 'ON' : 'OFF'}</span>`;
  }));
  if (!bits.length) return '<p class="rbempty">Waiting for the first device response.</p>';
  const linkSpec = mixerLinkReadbackSpec();
  const inputSpec = inputLinkReadbackSpec();
  const mixerMapped = linkSpec && layout.safe
    && Number(layout.category) === Number(linkSpec.category)
    && Number(layout.index) === Number(linkSpec.index);
  const inputMapped = inputSpec && layout.safe
    && Number(layout.category) === Number(inputSpec.category)
    && Number(layout.index) === Number(inputSpec.index);
  const note = mixerMapped
    ? 'ON means the returned selector byte is non-zero; a complete bitmap seeds the visible mixer-pair links.'
    : inputMapped
      ? 'ON means the returned pair byte is non-zero; a complete table seeds the mapped preamp and ADAT links.'
      : 'ON means the returned byte is non-zero; polarity and transition correlation remain provisional.';
  return `<div class="rbvalues">${bits.join('')}</div>`
    + `<p class="rbnote">${note}</p>`;
}

function rbMicBody(entries) {
  const rows = entries.flatMap(([, records]) => records).map(record => {
    const model = emuModelName(Number(record.emu_model));
    return `<tr><td>${rbNum(record.record_index)}</td><td>${rbNum(record.target)}</td>`
      + `<td>${rbEscape(model)} <span class="rbcat">(${rbNum(record.emu_model)})</span></td>`
      + `<td>${Number(record.ch_swap) ? 'ON' : 'OFF'}</td><td>${rbNum(record.pattern)}</td>`
      + `<td>${rbEscape(record.raw || '–')}</td></tr>`;
  });
  if (!rows.length) return '<p class="rbempty">Waiting for the first device response.</p>';
  return `<table class="rbtable"><thead><tr><th>tap</th><th>target</th><th>model</th><th>swap</th><th>pattern</th><th>raw</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
}

function rbAfxInstanceBody(layout, entries) {
  const records = entries.flatMap(([, values]) => values);
  if (!records.length) return '<p class="rbempty">Waiting for the first device response.</p>';
  const active = records.filter(record => Number(record.inst_count) !== 0);
  const table = active.length
    ? `<table class="rbtable"><thead><tr><th>type</th><th>instances</th><th>raw</th></tr></thead><tbody>${active.map(record =>
        `<tr><td>${rbNum(record.type_id)}</td><td class="num">${rbNum(record.inst_count)}</td><td>${rbEscape(record.raw || '–')}</td></tr>`).join('')}</tbody></table>`
    : '<p class="rbempty">All returned instance counts are zero.</p>';
  return `<p class="rbnote">${records.length} records; ${active.length} non-zero</p>${table}`;
}

function rbAfxStripBody(entries) {
  const populated = entries.flatMap(([outer, records]) => {
    const slots = records.filter(record => Number(record.type) !== 0 || Number(record.inst) !== 0);
    return slots.length ? [{outer, slots}] : [];
  });
  if (!entries.length) return '<p class="rbempty">Waiting for the first device response.</p>';
  if (!populated.length) return `<p class="rbempty">No populated slots in the ${entries.length} cached strip response${entries.length === 1 ? '' : 's'}.</p>`;
  return `<div class="rbstrips">${populated.map(({outer, slots}) =>
    `<div class="rbstrip"><b>strip ${rbEscape(outer)}</b><span>${slots.map(record =>
      `slot ${record.record_index}: type ${rbNum(record.type)} / inst ${rbNum(record.inst)} `
      + `<span class="rbcat">(${rbEscape(record.raw || '–')})</span>`).join(' · ')}</span></div>`).join('')}</div>`;
}

function rbGenericBody(entries, layout) {
  const rows = entries.flatMap(([outer, records]) => records.map(record =>
    `<tr><td>${rbEscape(outer)}:${rbNum(record.record_index)}</td><td>${rbEscape(record.raw || '–')}</td>`
    + `<td>${Object.entries(record).filter(([key]) => key !== 'record_index' && key !== 'raw')
      .map(([key, value]) => `${rbEscape(key)}=${rbEscape(value)}`).join(' ')}</td></tr>`));
  if (!rows.length) return '<p class="rbempty">Waiting for the first device response.</p>';
  return `<table class="rbtable"><thead><tr><th>outer:record</th><th>raw</th><th>fields</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
}

function rbLayoutBody(layout) {
  if (!layout.safe) {
    return `<p class="rbempty">The response shape is documented, but the outer query ${rbEscape(rbLayoutBound(layout))} is still capture-required. No probe was sent.</p>`;
  }
  const entries = rbCurrentEntries(layout);
  switch (layout.kind) {
    case 'link_table': return rbLinkBody(layout, entries);
    case 'mic_emulations': return rbMicBody(entries);
    case 'afx_instance_counts': return rbAfxInstanceBody(layout, entries);
    case 'afx_strip_order': return rbAfxStripBody(entries);
    default: return rbGenericBody(entries, layout);
  }
}

function renderStructuredReadbacks() {
  const section = $('#readbacksec'), box = $('#readbacks');
  const layouts = STRUCTURED?.layouts || [];
  if (!section || !box) return;
  section.hidden = !layouts.length;
  if (!layouts.length) { box.innerHTML = ''; return; }
  box.innerHTML = layouts.map(layout => {
    const category = rbHex(layout.category);
    const status = layout.safe
      ? `<span class="rbsafe">safe outer query</span>`
      : `<span class="rbcapture">capture required</span>`;
    return `<article class="rbcard"><h3>${rbEscape(layout.name)} <span class="rbcat">${category}</span></h3>`
      + `<p class="rbmeta">${rbEscape(rbLayoutBound(layout))} · ${status} · ${rbEscape(layout.status || 'status unknown')}</p>`
      + rbLayoutBody(layout) + '</article>';
  }).join('');
}

async function reloadReadback() {
  [ROUTING, MIXER, AURAVERB, STRUCTURED] = await Promise.all([
    getJSON('/api/routing'), getJSON('/api/mixer'), getJSON('/api/auraverb'),
    getJSON('/api/readbacks')]);
  reloadSurround().catch(() => {});
  syncMixerLinksFromReadback(STRUCTURED);
  syncInputLinksFromReadback(STRUCTURED);
  renderStructuredReadbacks();
  initAuraVerbPanel();
  const rh = routingHome();
  if (!rh || !rh.children.length || (!RG_POPPED && !rh.querySelector('#rmx'))) buildRouting(); else refreshRouting();
  if (!$('#mixer').children.length) buildMixer(); else refreshMixer();
}

// ---- state fan-out ---------------------------------------------------
function applyState(s) {
  const wasOnline = ONLINE;
  ONLINE = !!s.online;
  const st = $('#status');
  st.className = ONLINE ? 'online' : 'offline';
  st.textContent = ONLINE ? 'online' : 'device offline';
  $('#main').classList.toggle('offline', !ONLINE);
  if (!ONLINE) {
    applyMeters([]); applyMixerMeters(null); applyOutputMeters(null);
    reportMessage('connection', 'Device connection', 'The device is offline.');
    return;
  }
  if (!wasOnline) clearMessage('connection');

  applyChannels(s.channels);
  applyMeters(s.input_meters || s.meters_db);
  applyMixerMeters(s.mixer_meters);
  if (METER_DEBUG) applyMeterDebug(s);
  applyBuses(s.buses);
  applyOutputMeters(s.output_meters);
  applyDig('adat', s.adat);
  applyDig('spdif', s.spdif);
  applySettings(s);
  applyClock(s);

  if (typeof s.brightness === 'number' && document.activeElement !== $('#bright')) {
    $('#bright').value = s.brightness;
    $('#brightval').textContent = s.brightness;
  }

  let readbackChanged = !wasOnline;
  if (s.rb_ver !== undefined && s.rb_ver !== RB_VER) {
    RB_VER = s.rb_ver;
    readbackChanged = true;
  }
  if (s.link_rb_ver !== undefined && s.link_rb_ver !== LINK_RB_VER) {
    LINK_RB_VER = s.link_rb_ver;
    readbackChanged = true;
  }
  if (readbackChanged) {
    reloadReadback().catch(() => {});
  }
}

$('#bright').addEventListener('change', e => post('/api/brightness', {value: +e.target.value}));
