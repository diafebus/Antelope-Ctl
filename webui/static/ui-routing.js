"use strict";

// ---- routing matrix (Phase 1: per-destination grid) -----------------
// Rows = sources (grouped, collapsible); columns = the selected dest's
// output channels. Routing is EXCLUSIVE per output channel -> exactly one
// lit cell per column (or the MUTE row). Click empty -> route; click the
// lit cell -> mute. A route write triggers an immediate device readback
// (rb_ver bump), so verified/differs resolves off the very next poll.

const SRC_FAM = {                     // kind -> family (colour + row grouping)
  preamp: 'pre', emumic: 'emu', compplay: 'play', adat: 'adat', afx: 'afx',
  surround: 'sur', osc: 'osc', spdif: 'spdif',
  mix1: 'mix', mix2: 'mix', mix3: 'mix', mix4: 'mix', mute: 'mute',
};
let SRC_GROUPS = null;                // built once from ROUTING.sources
function buildSrcGroups() {
  if (SRC_GROUPS) return SRC_GROUPS;
  const byKind = {};
  ROUTING.sources.forEach(s => { byKind[s.kind] = s; });
  const rowsFor = s => s.stereo
    ? [{ key: `${s.kind}:L`, label: `${s.label || s.kind} L`, kind: s.kind, number: 'L' },
       { key: `${s.kind}:R`, label: `${s.label || s.kind} R`, kind: s.kind, number: 'R' }]
    : Array.from({ length: s.count }, (_, i) => {
        const n = s.base + i;
        return { key: `${s.kind}:${n}`, label: `${s.label || s.kind} ${n}`, kind: s.kind, number: n };
      });
  const g = [];
  const add = (kind, fallback) => {
    if (!byKind[kind]) return;
    const name = byKind[kind].group_label || byKind[kind].label || fallback;
    g.push({ key: kind, name, fam: SRC_FAM[kind] || 'unknown', rows: rowsFor(byKind[kind]) });
  };
  add('preamp', 'Preamps');
  add('emumic', 'EmuMic');
  add('compplay', 'Playback');
  add('adat', 'ADAT in');
  add('afx', 'AFX out');
  add('surround', 'Surround out');
  add('osc', 'Oscillator');
  add('spdif', 'S/PDIF in');
  const mixes = ['mix1', 'mix2', 'mix3', 'mix4'].filter(k => byKind[k]).flatMap(k => rowsFor(byKind[k]));
  if (mixes.length) {
    const names = ['mix1', 'mix2', 'mix3', 'mix4'].filter(k => byKind[k])
      .map(k => byKind[k].group_label || byKind[k].label || k);
    g.push({ key: 'mixes', name: names.join(' / ') || 'Mixes 1-4', fam: 'mix', rows: mixes });
  }
  // Keep the familiar ordering above, but do not make a new profile edit this
  // launcher just because it introduces another source-bank semantic.
  const knownKinds = new Set([
    'preamp', 'emumic', 'compplay', 'adat', 'afx', 'surround', 'osc', 'spdif',
    'mix1', 'mix2', 'mix3', 'mix4', 'mute',
  ]);
  ROUTING.sources.filter(s => !knownKinds.has(s.kind))
    .forEach(s => add(s.kind, s.label || s.kind));
  SRC_GROUPS = g;
  return g;
}

// "preamp 3" -> "preamp:3"  ·  "spdif L" -> "spdif:L"  ·  "MUTE" -> "mute:"
// Unknown profile banks stay visible as raw keys instead of becoming a blank
// cell.  That is important on Zen Go: bank 0x03 is seen in the default map,
// but is not decoded well enough to relabel it as a preamp or playback source.
function rawRouteParts(label) {
  const m = String(label || '').match(/^bank\s+(0x[0-9a-f]+)\s+idx\s+(\d+)$/i);
  return m ? {bank: m[1].toLowerCase(), idx: +m[2]} : null;
}
function rawSourceKey(route) {
  const bank = Number(route?.bank), idx = Number(route?.idx);
  return Number.isFinite(bank) && Number.isFinite(idx)
    ? `raw:${bank.toString(16).padStart(2, '0')}:${idx}` : '';
}
function rawKeyParts(key) {
  const m = String(key || '').match(/^raw:([0-9a-f]+):(\d+)$/i);
  return m ? {bank: m[1].toUpperCase().padStart(2, '0'), idx: +m[2]} : null;
}
function rawSourceLabel(key) {
  const p = rawKeyParts(key);
  return p ? `DEVICE SOURCE 0x${p.bank} / ${p.idx + 1} (UNMAPPED)` : 'UNMAPPED SOURCE';
}
function labelToKey(label) {
  if (!label) return '';
  const text = String(label).trim();
  if (text.toUpperCase() === 'MUTE') return 'mute:';
  const raw = rawRouteParts(text);
  if (raw) return `raw:${raw.bank}:${raw.idx}`;
  // Prefer the profile's stable source key. Labels may contain spaces (for
  // example "COMPUTER PLAY 1"), so parsing the display text is only a legacy
  // fallback for older daemons/profiles.
  for (const source of ROUTING?.sources || []) {
    const prefix = String(source.label || source.kind || '').trim();
    const lower = text.toLowerCase(), prefixLower = prefix.toLowerCase();
    if (!prefix || !lower.startsWith(prefixLower + ' ')) continue;
    const suffix = text.slice(prefix.length).trim();
    if (source.stereo && /^[LR]$/i.test(suffix)) return `${source.kind}:${suffix.toUpperCase()}`;
    if (!source.stereo && /^\d+$/.test(suffix)) return `${source.kind}:${suffix}`;
  }
  const m = text.match(/^(\S+)\s+(\S+)$/);
  return m ? `${m[1].toLowerCase()}:${m[2]}` : '';
}
const SHORT_FAM = { preamp: 'Pre', emumic: 'Emu', compplay: 'CP', adat: 'AD', afx: 'FX',
                    surround: 'Sur', osc: 'Osc', spdif: 'SP', mix1: 'M1', mix2: 'M2', mix3: 'M3', mix4: 'M4' };
function shortLabel(label) {
  if (!label || String(label).trim().toUpperCase() === 'MUTE') return '—';
  const raw = rawRouteParts(label);
  if (raw) return `U${raw.bank.slice(2).toUpperCase()}/${raw.idx + 1}`;
  const stable = labelToKey(label);
  if (stable && !stable.startsWith('raw:')) return keyShort(stable);
  const m = label.match(/^(\S+)\s+(\S+)$/);
  const kind = m ? m[1].toLowerCase() : '';
  return m ? `${SHORT_FAM[kind] || m[1]} ${m[2]}` : label;
}
function routeKey(route) { return route?.key || labelToKey(route?.label); }
// a want-key ("preamp:3", "mute:") -> short cell text / family, for optimistic paint
function keyShort(key) {
  if (key === 'mute:') return '✕';
  if (key.startsWith('raw:')) return rawSourceLabel(key).replace('DEVICE SOURCE ', 'U');
  const [k, n] = key.split(':'); return `${SHORT_FAM[k] || k} ${n}`;
}
function keyFam(key) {
  if (key === 'mute:') return 'mute';
  return key.startsWith('raw:') ? 'unknown' : (SRC_FAM[key.split(':')[0]] || 'unknown');
}
function labelFam(label) { return label ? keyFam(labelToKey(label)) : 'none'; }
// tight grid-cell tag: 1-letter family + number ("P12", "C32", "SL"), colour carries the rest
const GRID_TAG = { preamp: 'P', emumic: 'E', compplay: 'C', adat: 'A', afx: 'F',
                   surround: 'R', osc: 'O', spdif: 'S', mix1: 'm1', mix2: 'm2', mix3: 'm3', mix4: 'm4' };
function cellTag(key) {
  if (!key) return '·';
  if (key === 'mute:') return '✕';
  if (key.startsWith('raw:')) {
    const p = rawKeyParts(key);
    return p ? `U${p.bank}/${p.idx + 1}` : '?';
  }
  const [k, n] = key.split(':');
  return (GRID_TAG[k] || (k[0] || '?').toUpperCase()) + n;
}

// a write resolves the instant a readback newer than it lands (RB_VER advanced);
// RT_TIMEOUT_MS is only the fallback if no readback ever comes.
const RT_TIMEOUT_MS = 2500, RT_FLASH_MS = 450;

const ROUTE_GRP_OPEN = (() => {
  try { return new Set(JSON.parse(localStorage.getItem('routeGroups') || '[]')); } catch (_) { return new Set(); }
})();
const ROUTE_PENDING = {};            // "D:ch" -> {want, ts}
let ROUTE_DEST = 0;

const curFor = destId => ((ROUTING && ROUTING.current) || {})[String(destId)] || [];
function grpCount(grp, cur) {
  const keys = new Set(grp.rows.map(r => r.key));
  return cur.reduce((n, c) => n + (c && keys.has(routeKey(c)) ? 1 : 0), 0);
}

// The routing UI (toolbar + matrix + grid) lives in #routing, which is either
// inline in the page or -- when popped out -- a fresh #routing inside a
// detached browser window. routingHome() / rq() always resolve to the live one.
let RG_POPPED = false;
let RG_WIN = null, RG_WIN_TIMER = 0;
function routingHome() {
  if (RG_WIN && !RG_WIN.closed) {
    try { const r = RG_WIN.document.getElementById('routing'); if (r) return r; } catch (_) {}
  }
  return document.getElementById('routing');
}
const rgDoc = () => { const h = routingHome(); return h ? h.ownerDocument : document; };
const rq = sel => { const h = routingHome(); return h ? h.querySelector(sel) : null; };
const rqa = sel => { const h = routingHome(); return h ? [...h.querySelectorAll(sel)] : []; };
const rgHost = () => rq('#rpb');

function buildRouting() {
  const wrap = routingHome();
  if (!wrap) return;
  buildSrcGroups();
  if (!ROUTING.dests.some(d => d.id === ROUTE_DEST)) ROUTE_DEST = ROUTING.dests[0] ? ROUTING.dests[0].id : 0;
  wrap.innerHTML = `
    <div class="rtop">
      <div class="rviews">
        <button class="rvbtn" data-view="grid">Grid</button>
        <button class="rvbtn" data-view="matrix">Matrix</button>
      </div>
    </div>
    <div id="rmx" class="rmxwrap"></div>
    <div id="rpb" class="rpbwrap"></div>`;
  wrap.querySelectorAll('.rvbtn').forEach(b => b.addEventListener('click', () => setRouteView(b.dataset.view)));
  setRouteView(ROUTE_VIEW);
}

function setRouteView(v) {
  ROUTE_VIEW = (v === 'matrix') ? 'matrix' : 'grid';
  try { localStorage.setItem('routeView', ROUTE_VIEW); } catch (_) {}
  rqa('.rvbtn').forEach(b => b.classList.toggle('on', b.dataset.view === ROUTE_VIEW));
  const mx = ROUTE_VIEW === 'matrix';
  const rmx = rq('#rmx'), rpb = rgHost();
  if (rmx) rmx.hidden = !mx;
  if (rpb) rpb.hidden = mx;
  if (mx) renderMatrix(); else renderGrid();
}

// ---- routing pop-out window --------------------------------------------
// A real, detachable browser window (drag it to another monitor) holding the
// full routing UI -- Grid and Matrix both. Its DOM is disposable: we rebuild
// #routing from ROUTING data on open and on close, so nothing is ever lost if
// the window is closed abruptly.
function openRoutePopup() {
  if (RG_WIN && !RG_WIN.closed) { RG_WIN.focus(); return; }
  const ww = 1400, wh = 900;
  const lx = Math.max(0, Math.round((screen.availWidth - ww) / 2 + (screen.availLeft || 0)));
  const ly = Math.max(0, Math.round((screen.availHeight - wh) / 2 + (screen.availTop || 0)));
  // popup=yes + no toolbar/menubar/location asks the browser for a chromeless
  // window (no address bar). Chrome/Edge honour it fully; Firefox still shows a
  // slim read-only origin strip that it won't let script remove.
  const feat = `popup=yes,location=no,toolbar=no,menubar=no,status=no,` +
               `scrollbars=yes,resizable=yes,width=${ww},height=${wh},left=${lx},top=${ly}`;
  const w = window.open('', 'antelopeRouting', feat);
  if (!w) { alert('The routing window was blocked — allow pop-ups for this page, then try again.'); return; }
  const d = w.document;
  d.open();
  d.write('<!doctype html><html><head><meta charset="utf-8"><title>Routing — antelope-ctl</title>' +
    '<link rel="stylesheet" href="/webui/static/app.css"><style>html,body{margin:0}body{padding:14px;background:var(--bg);color:var(--fg);' +
    'font:14px system-ui,sans-serif}.pbhint{margin-top:0}.rtop{margin-bottom:12px}</style>' +
    '</head><body><div id="routing"></div></body></html>');
  d.close();
  RG_WIN = w;
  RG_POPPED = true;
  const main = document.getElementById('routing');
  if (main) {
    main.innerHTML = '';
    const away = document.createElement('div');
    away.id = 'rpbaway'; away.className = 'rpbwrap';
    away.innerHTML = '<p class="pbhint">Routing is open in a separate window. ' +
      '<button type="button" id="rpbback" class="secbtn">Bring it back</button></p>';
    main.appendChild(away);
    away.querySelector('#rpbback').addEventListener('click', () => closeRoutePopup());
  }
  $('#routepop').classList.add('on');
  buildRouting();
  w.addEventListener('pagehide', () => closeRoutePopup(true), { once: true });
  RG_WIN_TIMER = setInterval(() => { if (!RG_WIN || RG_WIN.closed) closeRoutePopup(true); }, 700);
}

function closeRoutePopup(fromWin) {
  if (!RG_POPPED) return;
  RG_POPPED = false;
  if (RG_WIN_TIMER) { clearInterval(RG_WIN_TIMER); RG_WIN_TIMER = 0; }
  const w = RG_WIN;
  RG_WIN = null;
  if (w && !w.closed && !fromWin) w.close();
  const away = document.getElementById('rpbaway'); if (away) away.remove();
  $('#routepop').classList.remove('on');
  buildRouting();                                     // rebuild inline from ROUTING
}
window.addEventListener('pagehide', () => { if (RG_WIN && !RG_WIN.closed) RG_WIN.close(); });
$('#routepop').innerHTML = POPOUT_ICON + '<span>Full view</span>';
$('#routepop').addEventListener('click', openRoutePopup);

// ---- collapsible sections (data-min points at the body element's id) -----
function wireMinButtons() {
  $$('.secmin[data-min]').forEach(btn => {
    const body = document.getElementById(btn.dataset.min);
    if (!body) return;
    const key = 'min:' + btn.dataset.min;
    const set = min => {
      body.classList.toggle('min', min);
      btn.textContent = min ? '+' : '–';
      btn.title = min ? 'expand this section' : 'collapse this section';
      btn.setAttribute('aria-expanded', String(!min));
      try { localStorage.setItem(key, min ? '1' : '0'); } catch (_) {}
    };
    btn.addEventListener('click', () => set(!body.classList.contains('min')));
    try {
      const saved = localStorage.getItem(key);
      if (saved === '1' || saved === '0') set(saved === '1');
    } catch (_) {}
  });
}
wireMinButtons();

// ---- routing sub-tabs (profile-sized Routing | Mix N) --------------------
function initRouteTabs() {
  const bar = $('#routetabs'); if (!bar) return;
  const show = name => {
    bar.querySelectorAll('.tabbtn').forEach(b => b.classList.toggle('active', b.dataset.rtab === name));
    const mix = /^mix(\d+)$/.exec(name);
    const paneName = mix ? 'mixers' : name;
    $$('[data-rpane]').forEach(p => { p.hidden = p.dataset.rpane !== paneName; });
    if (mix && MIXER && $('#mixer').children.length) selectMixer(+mix[1] - 1);
    try { localStorage.setItem('routeTab', name); } catch (_) {}
  };
  bar.addEventListener('click', e => { const b = e.target.closest('.tabbtn'); if (b) show(b.dataset.rtab); });
  let saved = null; try { saved = localStorage.getItem('routeTab'); } catch (_) {}
  const savedTab = saved && bar.querySelector(`.tabbtn[data-rtab="${saved}"]`);
  const first = [...bar.querySelectorAll('.tabbtn')].find(b => !b.hidden);
  show(savedTab && !savedTab.hidden ? saved : (first?.dataset.rtab || 'matrix'));
}
initRouteTabs();

function renderMatrix() {
  const d = ROUTING.dests.find(x => x.id === ROUTE_DEST);
  if (!d) return;
  const cur = curFor(d.id), N = d.channels;
  const muteLabel = ROUTING.sources.find(s => s.kind === 'mute')?.label || 'MUTE';
  const colName = ch => (d.stereo && ch < 2) ? (ch ? 'R' : 'L') : ch + 1;

  const cellRow = row => `<tr data-src="${row.key}" class="fam-${SRC_FAM[row.kind] || 'mute'}">
    <th class="k">${row.kind === 'mute' ? row.label : shortLabel(row.label)}</th>${
      Array.from({ length: N }, (_, ch) => {
        const on = cur[ch] && routeKey(cur[ch]) === row.key;
        const p = ROUTE_PENDING[d.id + ':' + ch];
        return `<td class="c${on ? ' on' : ''}${p && p.want === row.key ? ' pending' : ''}" data-ch="${ch}"></td>`;
      }).join('')}</tr>`;

  const destLabel = d.label || d.name || ('dest' + d.id);
  const destTitle = destLabel.replace(/_/g, ' ').toUpperCase();
  let h = `<div class="rdtitle">
      <label class="rdsel">Destination
        <select id="rdest">${ROUTING.dests.map(x =>
          `<option value="${x.id}"${x.id === ROUTE_DEST ? ' selected' : ''}>${(x.label || x.name || ('dest' + x.id)).replace(/_/g, ' ')} — ${x.channels} ch</option>`).join('')}</select>
      </label>
      <span class="rdmeta">outputs across the top · sources down the side · one per output</span>
    </div>
    <table class="rmx"><thead><tr><th class="cnr">source ↓</th>${
    Array.from({ length: N }, (_, ch) => {
      const lab = cur[ch] ? cur[ch].label : '';
      const fam = labelFam(lab);
      return `<th data-ch="${ch}"><span class="cn">${colName(ch)}</span><span class="cs fam-${fam}">${lab ? shortLabel(lab) : ''}</span></th>`;
    }).join('')}</tr></thead><tbody>`;

  h += cellRow({ key: 'mute:', label: muteLabel, kind: 'mute', number: null });
  SRC_GROUPS.forEach(grp => {
    const open = ROUTE_GRP_OPEN.has(grp.key);
    const n = grpCount(grp, cur);
    const m = Math.min(N, grp.rows.length);
    h += `<tr class="grp"><th colspan="${N + 1}"><div class="grph">
      <button class="gtog" data-grp="${grp.key}"><span class="tw">${open ? '▾' : '▸'}</span>${grp.name}<span class="gc${n ? ' has' : ''}">${n}/${grp.rows.length}</span></button>
      <button class="gop" data-g11="${grp.key}" title="route ${grp.name} 1:1 -> ${destTitle} ch 1..${m}">1:1</button>
    </div></th></tr>`;
    if (open) h += grp.rows.map(cellRow).join('');
  });
  h += `</tbody></table>`;

  const box = rq('#rmx');
  if (!box) return;
  box.innerHTML = h;
  const sel = box.querySelector('#rdest');
  if (sel) sel.addEventListener('change', e => { ROUTE_DEST = +e.target.value; renderMatrix(); });
  box.querySelectorAll('button[data-grp]').forEach(b => b.addEventListener('click', () => {
    const k = b.dataset.grp;
    ROUTE_GRP_OPEN.has(k) ? ROUTE_GRP_OPEN.delete(k) : ROUTE_GRP_OPEN.add(k);
    try { localStorage.setItem('routeGroups', JSON.stringify([...ROUTE_GRP_OPEN])); } catch (_) {}
    renderMatrix();
  }));
  box.querySelectorAll('button[data-g11]').forEach(b => b.addEventListener('click', () => {
    const grp = SRC_GROUPS.find(g => g.key === b.dataset.g11);
    const m = Math.min(N, grp.rows.length);
    routeBatch(d.id, grp.rows.slice(0, m).map((r, i) => ({ channel: i, kind: r.kind, number: r.number })));
  }));
  box.querySelectorAll('td.c').forEach(cell => cell.addEventListener('click', () => {
    const ch = +cell.dataset.ch;
    const [kind, num] = cell.closest('[data-src]').dataset.src.split(':');
    const wasOn = cell.classList.contains('on');
    if (wasOn && kind === 'mute') return;                 // already muted
    routeSet(d.id, ch, wasOn
      ? { kind: 'mute', number: null }
      : { kind, number: /^\d+$/.test(num) ? +num : (num || null) });
  }));
}

function routeSet(destId, ch, t) {
  const want = t.kind === 'mute' ? 'mute:' : `${t.kind}:${t.number}`;
  ROUTE_PENDING[destId + ':' + ch] = { want, ts: Date.now(), ver: RB_VER };
  const mbox = rq('#rmx');
  if (mbox) mbox.querySelectorAll(`td.c[data-ch="${ch}"]`).forEach(c => {   // optimistic: light the column
    const on = c.closest('[data-src]').dataset.src === want;
    c.classList.toggle('on', on);
    c.classList.toggle('pending', on);
  });
  gridMarkPending(destId, ch, want);
  post('/api/route', { dest: destId, channel: ch, kind: t.kind, number: t.number });
}

// several changes to one destination in a single read-modify-write (matrix
// group ops: 1:1 / Mute all). Same PENDING + flash resolution as routeSet.
function routeBatch(destId, changes) {
  if (!changes.length) return;
  const box = rq('#rmx');
  changes.forEach(c => {
    const want = c.kind === 'mute' ? 'mute:' : `${c.kind}:${c.number}`;
    ROUTE_PENDING[destId + ':' + c.channel] = { want, ts: Date.now(), ver: RB_VER };
    if (box) box.querySelectorAll(`td.c[data-ch="${c.channel}"]`).forEach(cell => {
      const on = cell.closest('[data-src]').dataset.src === want;
      cell.classList.toggle('on', on);
      cell.classList.toggle('pending', on);
    });
    gridMarkPending(destId, c.channel, want);
  });
  post('/api/route-batch', { dest: destId, changes });
}

function flashCell(ch, state, title) {
  const cur = curFor(ROUTE_DEST);
  const onKey = cur[ch] ? routeKey(cur[ch]) : '';
  const fbox = rq('#rmx'); if (!fbox) return;
  fbox.querySelectorAll(`td.c[data-ch="${ch}"]`).forEach(c => {
    c.classList.remove('pending');
    if (c.closest('[data-src]').dataset.src === onKey) {
      if (title) c.title = title; else c.removeAttribute('title');
      c.classList.add('flash-' + state);
      setTimeout(() => c.classList.remove('flash-' + state), RT_FLASH_MS);
    }
  });
}

function refreshRouting() {
  if (ROUTE_VIEW !== 'matrix') {
    const sig = JSON.stringify((ROUTING && ROUTING.current) || {});
    if (rgHost() && !rgHost().hidden && !RG_DRAG && sig !== RG_SIG) renderGrid();
    // verified / differs on the destination cells that a write touched
    Object.keys(ROUTE_PENDING).forEach(key => {
      const [dd, ch] = key.split(':').map(Number);
      const p = ROUTE_PENDING[key], age = Date.now() - p.ts, fresh = RB_VER > p.ver;
      const actual = curFor(dd)[ch] ? routeKey(curFor(dd)[ch]) : '';
      if (fresh && actual === p.want) { gridFlash('d:' + dd + ':' + ch, 'ok'); delete ROUTE_PENDING[key]; }
      else if (fresh) { gridFlash('d:' + dd + ':' + ch, 'differ', 'device: ' + ((curFor(dd)[ch] || {}).label || '—')); delete ROUTE_PENDING[key]; }
      else if (age > RT_TIMEOUT_MS) { gridFlash('d:' + dd + ':' + ch, 'timeout'); delete ROUTE_PENDING[key]; }
    });
    return;
  }
  if (!rq('#rmx')) { buildRouting(); return; }
  const cur = curFor(ROUTE_DEST);
  const box = rq('#rmx');
  // re-light every visible cell
  box.querySelectorAll('tr[data-src]').forEach(tr => {
    const k = tr.dataset.src;
    tr.querySelectorAll('td.c').forEach(c => {
      const ch = +c.dataset.ch;
      c.classList.toggle('on', !!cur[ch] && routeKey(cur[ch]) === k);
    });
  });
  // column captions
  box.querySelectorAll('thead th[data-ch]').forEach(th => {
    const lab = cur[+th.dataset.ch] ? cur[+th.dataset.ch].label : '';
    const fam = labelFam(lab);
    const cs = th.querySelector('.cs');
    cs.textContent = lab ? shortLabel(lab) : '';
    cs.className = 'cs fam-' + fam;
  });
  // group counts
  box.querySelectorAll('button[data-grp]').forEach(b => {
    const grp = SRC_GROUPS.find(g => g.key === b.dataset.grp);
    const n = grpCount(grp, cur), gc = b.querySelector('.gc');
    gc.textContent = `${n}/${grp.rows.length}`;
    gc.classList.toggle('has', !!n);
  });
  // resolve pending -> verified / differs / timeout
  Object.keys(ROUTE_PENDING).forEach(key => {
    const [dd, ch] = key.split(':').map(Number);
    if (dd !== ROUTE_DEST) { delete ROUTE_PENDING[key]; return; }
    const p = ROUTE_PENDING[key];
    const age = Date.now() - p.ts, fresh = RB_VER > p.ver;
    const actual = cur[ch] ? routeKey(cur[ch]) : '';
    if (fresh && actual === p.want) { flashCell(ch, 'ok'); delete ROUTE_PENDING[key]; }
    else if (fresh) { flashCell(ch, 'differ', 'device: ' + (cur[ch] ? cur[ch].label : '—')); delete ROUTE_PENDING[key]; }
    else if (age > RT_TIMEOUT_MS) { flashCell(ch, 'timeout'); delete ROUTE_PENDING[key]; }
  });
}
// ---- routing grid (FROM / TO) ------------------------------------------
// Modelled on the Launcher's routing tab: every source group is a row of
// numbered cells (FROM), every destination group is a row whose cells show
// -- as a short name + family colour -- which source currently feeds them
// (TO). Drag a FROM cell onto a TO cell to route; drag a FROM row label
// onto a TO row label for a 1:1 batch; drop the MUTE row's ✕ to mute.
// Reuses routeSet / routeBatch / the readback (rb_ver) for verified/differs.
let ROUTE_VIEW = (() => { try { return localStorage.getItem('routeView') || 'grid'; } catch (_) { return 'grid'; } })();

const rgNum = key => key.split(':')[1] || '';
let RG_SIG = '';

function renderGrid() {
  const box = rgHost(); if (!box) return;
  RG_SIG = JSON.stringify((ROUTING && ROUTING.current) || {});
  const muteLabel = ROUTING.sources.find(s => s.kind === 'mute')?.label || 'MUTE';

  const fromRow = g => `<div class="rgrow">
    <div class="rglbl fam-${g.fam}" data-node="sg:${g.key}" tabindex="0" title="${g.name} — drag onto a destination row to map 1:1">${g.name}</div>
    <div class="rgcells">${g.rows.map(r =>
      `<div class="rgc fam-${g.fam}" data-node="${r.key}" tabindex="0" title="${r.label}">${rgNum(r.key)}</div>`).join('')}</div></div>`;

  const toRow = d => {
    const cur = curFor(d.id), N = d.channels;
    const nm = (d.label || d.name || ('dest' + d.id)).replace(/_/g, ' ').toUpperCase();
    return `<div class="rgrow">
      <div class="rglbl" data-node="dg:${d.id}" tabindex="0" title="${nm} (${N} ch)">${nm}</div>
      <div class="rgcells">${Array.from({ length: N }, (_, ch) => {
        const c = cur[ch], lab = c ? c.label : '';
        const fam = labelFam(lab);
        const cn = (d.stereo && ch < 2) ? (ch ? 'R' : 'L') : ch + 1;
        const pend = ROUTE_PENDING[d.id + ':' + ch] ? ' rgpending' : '';
        return `<div class="rgc rgto fam-${fam}${pend}" data-node="d:${d.id}:${ch}" tabindex="0" title="${nm} ${cn}  ◄  ${lab || '(none)'}">${lab ? cellTag(routeKey(c)) : '·'}</div>`;
      }).join('')}</div></div>`;
  };

  box.innerHTML = `
    <p class="pbhint"><b>Click a source</b> then <b>click a destination</b> — or drag one onto the other. Cell → cell routes one channel; row label → row label maps the group 1:1; <b>✕ MUTE</b> → a destination mutes it.</p>
    <div class="rgscroll">
      <div class="rgsec"><div class="rgsectitle">From — sources</div>
        ${SRC_GROUPS.map(fromRow).join('')}
        <div class="rgrow"><div class="rglbl rgmute" data-node="mute:" tabindex="0" title="drop onto a destination to mute it">✕ ${muteLabel}</div><div class="rgcells"><div class="rgc rgto fam-mute" data-node="mute:" tabindex="0" title="${muteLabel}">✕</div></div></div>
      </div>
      <div class="rgsec"><div class="rgsectitle">To — destinations</div>
        ${ROUTING.dests.map(toRow).join('')}
      </div>
    </div>`;

  box.querySelectorAll('.rgc, .rglbl').forEach(el => wireGridDrag(el));
  if (RG_ARMED) rgArmHighlight();          // survive a re-render mid-selection
}

// a source node is anything that isn't a destination-group / destination-channel
const rgIsDest = n => n.startsWith('dg:') || n.startsWith('d:');
const rgIsFrom = n => !rgIsDest(n);

// --- drag: document-level listeners, no setPointerCapture (elementFromPoint
//     is unreliable while a pointer is captured, which broke the drop) -------
let RG_DRAG = null, RG_JUST_DRAGGED = false;
function wireGridDrag(el) {
  el.addEventListener('pointerdown', e => {
    if (e.button != null && e.button !== 0) return;
    if (RG_DRAG) rgDragEnd();
    RG_JUST_DRAGGED = false;
    const doc = el.ownerDocument, node = el.dataset.node;
    // if this cell is part of a multi-cell selection, drag the whole selection
    const armed = (RG_ARMED && RG_ARMED.rows.length > 1 && RG_ARMED.rows.includes(node))
      ? { rows: RG_ARMED.rows.slice(), group: !!RG_ARMED.group } : null;
    RG_DRAG = { node, el, doc, armed, sx: e.clientX, sy: e.clientY, moved: false };
    doc.addEventListener('pointermove', rgDragMove, true);
    doc.addEventListener('pointerup', rgDragUp, true);
    doc.addEventListener('pointercancel', rgDragEnd, true);
  });
  el.addEventListener('click', e => rgGridClick(el, e));
}
function rgDragTargetAt(e) {
  let n = e.target;
  const hit = n && n.closest && n.closest('.rgdrop');
  if (hit) return hit;
  const over = RG_DRAG.doc.elementFromPoint(e.clientX, e.clientY);
  return (over && over.closest) ? over.closest('.rgdrop') : null;
}
function rgDragMove(e) {
  const D = RG_DRAG; if (!D) return;
  if (!D.moved && Math.hypot(e.clientX - D.sx, e.clientY - D.sy) < 5) return;
  const host = D.doc.getElementById('rpb'); if (!host) return;
  if (!D.moved) {
    D.moved = true;
    if (!D.armed) rgClearArmed();
    D.el.classList.add('rgdrag');
    const g = D.doc.createElement('div');
    g.className = 'pbghost ' + [...D.el.classList].filter(c => c.startsWith('fam-')).join(' ');
    g.textContent = D.armed ? `${D.armed.rows.length} channels` : (D.el.getAttribute('title') || D.el.textContent);
    D.doc.body.appendChild(g);
    D.ghost = g;
    const inFrom = rgIsFrom(D.node);
    host.querySelectorAll('.rgsec').forEach((sec, i) => {
      if ((i === 0) !== inFrom) sec.querySelectorAll('.rgc,.rglbl').forEach(x => x.classList.add('rgdrop'));
    });
  }
  D.ghost.style.left = e.clientX + 'px';
  D.ghost.style.top = e.clientY + 'px';
  host.querySelectorAll('.rgover').forEach(x => x.classList.remove('rgover'));
  const tgt = rgDragTargetAt(e);
  if (tgt) tgt.classList.add('rgover');
}
function rgDragUp(e) {
  const D = RG_DRAG;
  const tgt = (D && D.moved) ? rgDragTargetAt(e) : null;
  const moved = !!(D && D.moved), node = D && D.node, armed = D && D.armed;
  rgDragEnd();
  if (!moved) return;
  RG_JUST_DRAGGED = true;
  if (tgt) {
    if (armed) rgRoute(armed.rows, armed.group, tgt.dataset.node);
    else gridResolveDrop(node, tgt.dataset.node);
  }
  rgClearArmed();
}
function rgDragEnd() {
  const D = RG_DRAG; RG_DRAG = null;
  if (!D) return;
  D.doc.removeEventListener('pointermove', rgDragMove, true);
  D.doc.removeEventListener('pointerup', rgDragUp, true);
  D.doc.removeEventListener('pointercancel', rgDragEnd, true);
  D.el.classList.remove('rgdrag');
  if (D.ghost) D.ghost.remove();
  const host = D.doc.getElementById('rpb');
  if (host) host.querySelectorAll('.rgdrop,.rgover').forEach(x => x.classList.remove('rgdrop', 'rgover'));
}

// --- select then place: click a source (shift-click for a range), then click
//     or drag the selection onto a destination -----------------------------
// RG_ARMED = { rows:[srcKey,…] | ['mute:'], anchor:srcKey|null, group:bool }
let RG_ARMED = null;
const srcRowByKey = key => SRC_GROUPS.flatMap(g => g.rows).find(r => r.key === key);
const grpOfKey = key => SRC_GROUPS.find(g => g.rows.some(r => r.key === key));

function rgClearArmed() {
  const host = rgHost();
  if (host) host.querySelectorAll('.rgarmed,.rgdrop').forEach(x => x.classList.remove('rgarmed', 'rgdrop'));
  RG_ARMED = null;
}
function rgArmHighlight() {
  const host = rgHost(); if (!host || !RG_ARMED) return;
  host.querySelectorAll('.rgarmed').forEach(x => x.classList.remove('rgarmed'));
  RG_ARMED.rows.forEach(k => host.querySelectorAll(`[data-node="${cssq(k)}"]`).forEach(x => x.classList.add('rgarmed')));
  host.querySelectorAll('.rgsec').forEach((sec, i) => {
    if (i === 1) sec.querySelectorAll('.rgc,.rglbl').forEach(x => x.classList.add('rgdrop'));
  });
}
// normalise a single source node (drag / plain click) to the armed shape
function rgExpand(node) {
  if (node === 'mute:') return { rows: ['mute:'], anchor: null, group: false };
  if (node.startsWith('sg:')) {
    const g = SRC_GROUPS.find(x => 'sg:' + x.key === node);
    return { rows: g ? g.rows.map(r => r.key) : [], anchor: null, group: true };
  }
  return { rows: [node], anchor: node, group: false };
}
function rgGridClick(el, e) {
  if (RG_JUST_DRAGGED) { RG_JUST_DRAGGED = false; return; }   // swallow the click that trails a drag
  const node = el.dataset.node;
  if (rgIsFrom(node)) {
    if (e && e.shiftKey && RG_ARMED && RG_ARMED.anchor && !node.startsWith('sg:') && node !== 'mute:') {
      const g = grpOfKey(RG_ARMED.anchor);
      if (g && g.rows.some(r => r.key === node)) {            // extend the range within the group
        const keys = g.rows.map(r => r.key);
        const a = keys.indexOf(RG_ARMED.anchor), b = keys.indexOf(node);
        RG_ARMED.rows = keys.slice(Math.min(a, b), Math.max(a, b) + 1);
        RG_ARMED.group = false;
        rgArmHighlight();
        return;
      }
    }
    if (RG_ARMED && RG_ARMED.rows.length === 1 && RG_ARMED.rows[0] === node) { rgClearArmed(); return; }
    rgClearArmed();
    RG_ARMED = rgExpand(node);
    rgArmHighlight();
    return;
  }
  if (!RG_ARMED) return;                                       // a destination, nothing armed
  const { rows, group } = RG_ARMED;
  rgClearArmed();
  rgRoute(rows, group, node);
}

function gridFlash(dstNode, state, title) {
  const cell = pbNodeEl(`[data-node="${cssq(dstNode)}"]`);
  if (!cell) return;
  if (title) cell.title = title;
  cell.classList.remove('rgpending');
  cell.classList.add('rgflash-' + state);
  setTimeout(() => cell.classList.remove('rgflash-' + state), RT_FLASH_MS);
}
const cssq = s => (s + '').replace(/"/g, '\\"');
function pbNodeEl(sel) { const b = rgHost(); return b ? b.querySelector(sel) : null; }

// optimistic: repaint the TO cell to the new source the instant a route is
// queued, before the readback (rb_ver) lands and renderGrid repaints it for real.
function gridMarkPending(destId, ch, want) {
  const cell = pbNodeEl(`[data-node="${cssq('d:' + destId + ':' + ch)}"]`);
  if (!cell) return;
  if (want) {
    [...cell.classList].filter(c => c.startsWith('fam-')).forEach(c => cell.classList.remove(c));
    cell.classList.add('fam-' + keyFam(want));
    cell.textContent = cellTag(want);
  }
  cell.classList.add('rgpending');
}

// single dragged / clicked source node -> the unified router
function gridResolveDrop(sNode, dNode) {
  const { rows, group } = rgExpand(sNode);
  rgRoute(rows, group, dNode);
}

// rows: source keys (or ['mute:']).  group: rows came from a whole group.
// destNode: 'dg:<id>' (a whole row) or 'd:<id>:<ch>' (one channel; a list fills
// consecutively from there).
function rgRoute(rows, isGroup, destNode) {
  if (!rows || !rows.length) return;
  const isMute = rows.length === 1 && rows[0] === 'mute:';
  let did, startCh = null;
  if (destNode.startsWith('dg:')) did = +destNode.slice(3);
  else { const m = destNode.match(/^d:(\d+):(\d+)$/); if (!m) return; did = +m[1]; startCh = +m[2]; }
  const dest = ROUTING.dests.find(x => x.id === did); if (!dest) return;
  const N = dest.channels, dnm = (dest.label || dest.name || ('dest' + dest.id)).replace(/_/g, ' ');
  const ce = (key, ch) => isMute
    ? { channel: ch, kind: 'mute', number: null }
    : (r => r ? { channel: ch, kind: r.kind, number: r.number } : null)(srcRowByKey(key));

  if (startCh == null) {                                     // dropped on a whole destination row
    if (isMute) {
      if (!confirm(`Mute all ${N} outputs of ${dnm}?`)) return;
      routeBatch(did, Array.from({ length: N }, (_, ch) => ({ channel: ch, kind: 'mute', number: null })));
      return;
    }
    if (isGroup || rows.length > 1) {                        // N sources, 1:1 from channel 1
      const m = Math.min(N, rows.length);
      if (!confirm(`Route ${m} channel${m > 1 ? 's' : ''} 1:1 into ${dnm}?`)) return;
      routeBatch(did, rows.slice(0, m).map((k, i) => ce(k, i)).filter(Boolean));
      return;
    }
    const r = srcRowByKey(rows[0]); if (!r) return;          // one mono source -> fill every channel
    if (N > 2 && !confirm(`Feed ${r.label} into all ${N} outputs of ${dnm}?`)) return;
    routeBatch(did, Array.from({ length: N }, (_, ch) => ({ channel: ch, kind: r.kind, number: r.number })));
    return;
  }

  const changes = rows.map((k, i) => (startCh + i < N ? ce(k, startCh + i) : null)).filter(Boolean);
  if (!changes.length) return;
  if (changes.length === 1) routeSet(did, changes[0].channel, { kind: changes[0].kind, number: changes[0].number });
  else routeBatch(did, changes);
}
