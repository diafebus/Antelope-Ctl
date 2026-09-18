"use strict";

// Device settings and mic-modeling controls.

let MIC_MODELS = {};           // from /api/mic_models -- account-bound snapshot
// Which Antelope modelling mic is plugged in. The HID protocol has NO readback
// for this (or for model entitlements), so it's declared, not detected --
// seeded from mic_models.json user_owned, overridable + saved per viewer.
let EMU_MIC = null;
const MIC_LABEL = m => ({edge_solo:'Edge Solo', edge_duo:'Edge Duo', edge_note:'Edge Note',
                         edge_go:'Edge Go', verge:'Verge'}[m] || m);
function micInfo() { return (MIC_MODELS.modelling_mics || {})[EMU_MIC] || {}; }
const micHasPattern   = () => micInfo().pattern_control === true;   // dual-capsule only
const micConfirmed    = () => micInfo().confirmed === true;         // verified against the device
const micRequiresPair = () => micInfo().requires_pair === true;     // Edge Duo: uses a linked 7-8 / 9-10 / 11-12 pair
// the channels an emuMic action touches
function emuChans(ch) {
  if (micRequiresPair() && hasEmu(ch)) return [pairOf(ch) * 2, pairOf(ch) * 2 + 1];
  return isLinked(ch) ? [ch, partnerOf(ch)] : [ch];
}
function loadEmuMic() {
  try { return localStorage.getItem('preampEmuMic'); } catch (_) { return null; }
}
function saveEmuMic() { try { localStorage.setItem('preampEmuMic', EMU_MIC); } catch (_) {} }
function emuState(ch) { return Object.assign({on:false, model:0, pattern:50, swap:false}, EMU[ch]); }
function emuModelName(id) {
  const m = MIC_MODELS.models && MIC_MODELS.models[id];
  return m ? m.name : (id === 0 ? 'EdgeDuo (raw)' : 'Model ' + id);
}
function emuModelRange(id) {                       // [min,max] for byte [22]
  if (id === 0) return [0, 100];
  const r = (MIC_MODELS.pattern_index_ranges_2026_09_01) || {};
  if ((r['0_to_8'] || []).includes(id)) return [0, 8];
  if ((r['0_1_2'] || []).includes(id)) return [0, 2];
  if ((r['0_1_only_seen'] || []).includes(id)) return [0, 1];
  return [0, 0];                                   // fixed pattern
}
function emuDefaultPattern(id) {
  if (id === 0) return 50;
  const m = MIC_MODELS.models && MIC_MODELS.models[id];
  return (m && typeof m.pattern_class === 'number') ? m.pattern_class : 0;
}
function emuPatLabel(id, v) {
  if (id === 0) return v <= 2 ? 'omni' : v >= 98 ? 'fig-8'
    : Math.abs(v - 50) <= 2 ? 'cardioid' : v + '%';
  const [, max] = emuModelRange(id);
  return max === 0 ? 'fixed' : `${v} / ${max}`;
}
function pushEmu(ch) {
  if (!hasEmu(ch)) return;
  const s = emuState(ch);
  post('/api/emumic', {channel: ch, enabled: s.on, model: s.model,
                       pattern: s.pattern, swap: s.swap});
}
let emuSendTimer = null, emuSendLast = 0;
function applyEmu(ch, patch, {throttle = false} = {}) {
  if (!micConfirmed()) return;                    // panel is inert for unconfirmed mics
  // Edge Duo occupies both preamps of a pair -- link them when modeling goes on
  if (patch.on === true && micRequiresPair() && hasEmu(ch)) setLink(pairOf(ch), true);
  const chans = emuChans(ch);
  // mic modeling only works on a mic-mode input -- force it, whatever the mode
  // was (the Launcher does the same). Runs after any pair-link mode sync above.
  if (patch.on === true) chans.forEach(c => {
    const sel = preEl(c) && preEl(c).querySelector('[data-mode]');
    if (sel && sel.value !== 'mic') { sel.value = 'mic'; post('/api/mode', {channel: c, mode: 'mic'}); }
  });
  const merged = Object.assign(emuState(ch), patch);
  chans.forEach(c => { EMU[c] = Object.assign({}, merged); });
  saveEmu();
  refreshEmu();
  const send = () => { emuSendLast = Date.now(); emuSendTimer = null; chans.forEach(pushEmu); };
  if (!throttle) { clearTimeout(emuSendTimer); emuSendTimer = null; send(); return; }
  if (emuSendTimer) return;
  const wait = Math.max(0, 70 - (Date.now() - emuSendLast));
  if (wait === 0) send(); else emuSendTimer = setTimeout(send, wait);
}
function refreshEmu() {
  $$('.pre').forEach(el => {
    const ch = +el.dataset.ch, btn = el.querySelector('[data-emu]');
    if (!btn) return;
    // both channels of an Edge Duo pair tick together
    const on = emuOn(ch) || (micRequiresPair() && hasEmu(ch) && emuOn(partnerOf(ch)));
    btn.classList.toggle('on', on);
  });
  if (EMM.ch != null) syncEmuModal();
}

// the one shared settings panel
const EMM = { ch: null };
function openEmuModal(ch) {
  EMM.ch = ch;
  const sel = $('[data-emm-model]');
  if (!sel.options.length) {
    const ids = MIC_MODELS.models
      ? Object.keys(MIC_MODELS.models).filter(k => /^\d+$/.test(k)).map(Number).sort((a, b) => a - b)
      : [0];
    sel.innerHTML = ids.map(id => `<option value="${id}">${id}. ${emuModelName(id)}</option>`).join('');
  }
  const mic = $('[data-emm-mic]');
  if (!mic.options.length) {
    const mm = MIC_MODELS.modelling_mics || {};
    const fams = Object.keys(mm).filter(k => k[0] !== '_');
    mic.innerHTML = (fams.length ? fams : ['edge_duo']).map(f => {
      const ok = mm[f] && mm[f].confirmed === true;
      return `<option value="${f}"${ok ? '' : ' disabled'}>${MIC_LABEL(f)}${ok ? '' : ' — unsupported'}</option>`;
    }).join('');
    mic.value = EMU_MIC || mic.value;
  }
  syncEmuModal();
  $('#emumodal').hidden = false;
}
function closeEmuModal() { EMM.ch = null; $('#emumodal').hidden = true; }
function syncEmuModal() {
  const ch = EMM.ch; if (ch == null) return;
  const s = emuState(ch);
  const ok = micConfirmed();
  const pairChs = emuChans(ch);
  $('[data-emm-title]').textContent = (micRequiresPair() && pairChs.length === 2)
    ? `CH${pairChs[0] + 1}+CH${pairChs[1] + 1} — Mic Modeling`
    : `CH${ch + 1} — Mic Modeling`;
  $('[data-emm-mic]').value = EMU_MIC || '';

  const enB = $('[data-emm-enable]'), swB = $('[data-emm-swap]');
  const modelSel = $('[data-emm-model]'), pat = $('[data-emm-pat]'), pr = $('[data-emm-patrow]');
  enB.textContent = s.on ? 'ON' : 'OFF'; enB.classList.toggle('on', s.on); enB.disabled = !ok;
  modelSel.value = s.model; modelSel.disabled = !ok;
  swB.textContent = s.swap ? 'ON' : 'OFF'; swB.classList.toggle('on', s.swap);

  // single-capsule mics have no pattern morph / channel swap, whatever the model
  const patCap = ok && micHasPattern();
  const [, max] = emuModelRange(s.model);
  const patActive = patCap && max > 0;
  pr.style.opacity = patActive ? '1' : '.4';
  pat.min = 0; pat.max = max || 1; pat.disabled = !patActive; pat.value = s.pattern;
  $('[data-emm-patv]').textContent = !patCap ? 'n/a' : emuPatLabel(s.model, s.pattern);
  swB.disabled = !patCap;

  $('[data-emm-note]').textContent = !MIC_MODELS.models
    ? 'No model catalogue loaded (profiles/mic_models.json).'
    : !ok
      ? `${MIC_LABEL(EMU_MIC)}: emuMic isn’t verified against the device yet — controls disabled. Only the Edge Duo is supported so far.`
      : (micRequiresPair() ? 'Edge Duo uses both preamps of the pair (linked). ' : '')
        + 'This model list was captured on one Edge Duo account — other mics have their own emulations. Declared, not entitlement-detected; current device state is shown in Protocol readback (cat 0x16).';
}
$('[data-emm-close]').addEventListener('click', closeEmuModal);
document.addEventListener('keydown', e => { if (e.key === 'Escape' && EMM.ch != null) closeEmuModal(); });
// drag the panel by its header (non-blocking -- controls behind stay live)
(function dragEmuPanel() {
  const panel = $('#emumodal'), hd = panel.querySelector('.modal-hd');
  let dragging = false, dx = 0, dy = 0;
  hd.addEventListener('pointerdown', e => {
    if (e.target.closest('.modal-x')) return;
    const r = panel.getBoundingClientRect();
    dragging = true; dx = e.clientX - r.left; dy = e.clientY - r.top;
    panel.style.right = 'auto'; panel.style.left = r.left + 'px'; panel.style.top = r.top + 'px';
    hd.setPointerCapture(e.pointerId);
  });
  hd.addEventListener('pointermove', e => {
    if (!dragging) return;
    panel.style.left = Math.max(4, Math.min(innerWidth - 60, e.clientX - dx)) + 'px';
    panel.style.top  = Math.max(4, Math.min(innerHeight - 40, e.clientY - dy)) + 'px';
  });
  const stop = () => { dragging = false; };
  hd.addEventListener('pointerup', stop);
  hd.addEventListener('pointercancel', stop);
})();
// ---- settings gear panel: out trim, Line/Reamp levels, DC-coupling, brightness ----
const DC = { on: false };
function buildSettings() {
  const trimGrp = $('[data-set-trim]'), ot = PROFILE.params?.output_trim;
  if (trimGrp && ot?.id) {
    trimGrp.hidden = false;
    // index -> dBu output reference level, same scale on all 3 targets
    // (confirmed 2026-09-02). Fall back to the raw index if the profile is old.
    const dbu = ot.trim_dbu || {};
    const label = i => (dbu[i] != null ? dbu[i] + ' dBu' : String(i));
    $$('[data-trim]').forEach(sel => {
      sel.innerHTML = Array.from({ length: 7 }, (_, i) => `<option value="${i}">${label(i)}</option>`).join('');
      sel.addEventListener('change', () =>
        post('/api/output-trim', { target: +sel.dataset.trim, value: +sel.value }));
    });
  }
  const dc = $('[data-dc]');
  if (dc) {
    try { DC.on = localStorage.getItem('dcCoupled') === '1'; } catch (_) {}
    const paint = () => { dc.classList.toggle('on', DC.on); dc.textContent = DC.on ? 'ON' : 'OFF'; };
    paint();
    dc.addEventListener('click', () => {
      DC.on = !DC.on;
      try { localStorage.setItem('dcCoupled', DC.on ? '1' : '0'); } catch (_) {}
      paint();
      // Device readback is 0x73 byte 93 bit 0; this panel remains optimistic
      // until the state-report value is wired into its display state.
      post('/api/dc-coupling', { on: DC.on });
    });
  }
}
function applySettings(s) {
  if (!s || !s.trim) return;
  const tgt = { monitor_a: '0', monitor_b: '1', line_out: '2' };
  Object.entries(s.trim).forEach(([k, v]) => {
    const sel = $(`[data-trim="${tgt[k]}"]`);
    if (sel && document.activeElement !== sel) sel.value = v;
  });
}

// ---- settings gear (Line Out / Reamp output levels) ----
(function settingsPanel() {
  const btn = $('#gearbtn'), panel = $('#settings');
  if (!btn || !panel) return;
  btn.innerHTML = GEAR_ICON;
  const setOpen = open => { panel.hidden = !open; btn.classList.toggle('on', open); };
  btn.addEventListener('click', () => setOpen(panel.hidden));
  panel.querySelector('[data-set-close]').addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !panel.hidden) setOpen(false); });
  // drag by the header, same as the emuMic panel
  const hd = panel.querySelector('.modal-hd');
  let dragging = false, dx = 0, dy = 0;
  hd.addEventListener('pointerdown', e => {
    if (e.target.closest('.modal-x')) return;
    const r = panel.getBoundingClientRect();
    dragging = true; dx = e.clientX - r.left; dy = e.clientY - r.top;
    panel.style.right = 'auto'; panel.style.left = r.left + 'px'; panel.style.top = r.top + 'px';
    hd.setPointerCapture(e.pointerId);
  });
  hd.addEventListener('pointermove', e => {
    if (!dragging) return;
    panel.style.left = Math.max(4, Math.min(innerWidth - 60, e.clientX - dx)) + 'px';
    panel.style.top  = Math.max(4, Math.min(innerHeight - 40, e.clientY - dy)) + 'px';
  });
  const stop = () => { dragging = false; };
  hd.addEventListener('pointerup', stop);
  hd.addEventListener('pointercancel', stop);
})();

// ---- device clock: sample rate + clock source (header, next to the gear) ----
// Both are SET_GLOBAL enums with a 0x73 readback (sample_rate_idx /
// clock_source_idx), so no browser-side state -- the selects follow the
// device. The Orion IGNORES both writes while the host holds the USB audio
// interface streaming, and ignores the sample rate while the clock source is
// USB. When a change doesn't land within CLOCK_STUCK_MS we flag the select
// and show the release-audio instructions (see webui/NEXT.md, Linux quirk).
const CLOCK_STUCK_MS = 3500;
const CLK = { rate: null, src: null };   // { want, t } while a write is in flight

const srateLabel = hz => ((hz = +hz) % 1000 ? (hz / 1000).toFixed(1) : hz / 1000) + ' kHz';

function buildClockBar() {
  const bar = $('#clockbar');
  const sr = PROFILE.params?.sample_rate?.values;
  const cs = PROFILE.params?.clock_source?.values;
  if (!bar || (!sr && !cs)) return;
  const fill = (sel, obj, lbl, key) => {
    if (!obj) { sel.closest('label').hidden = true; return; }
    sel.innerHTML = Object.entries(obj).sort((a, b) => a[0] - b[0])
      .map(([k, v]) => `<option value="${k}">${lbl(v)}</option>`).join('');
    sel.addEventListener('change', () => sendClock(key, +sel.value));
  };
  fill($('#srate'), sr, srateLabel, 'rate');
  fill($('#csrc'), cs, v => String(v).split(' (')[0], 'src');   // "Oven (internal…)" -> "Oven"
  bar.hidden = false;
}

function sendClock(key, value) {
  CLK[key] = { want: value, t: Date.now() };
  clearMessage('clock');
  (key === 'rate' ? $('#srate') : $('#csrc')).classList.remove('stuck');
  post(key === 'rate' ? '/api/sample-rate' : '/api/clock-source', { value });
}

function applyClock(s) {
  let stuck = false;
  for (const [key, sel, idx] of [['rate', '#srate', s.sample_rate_idx],
                                 ['src', '#csrc', s.clock_source_idx]]) {
    if (typeof idx !== 'number') continue;
    const el = $(sel), pend = CLK[key];
    if (pend && idx === pend.want) { CLK[key] = null; el.classList.remove('stuck'); }
    else if (pend && Date.now() - pend.t > CLOCK_STUCK_MS) { el.classList.add('stuck'); stuck = true; }
    if (!CLK[key] && document.activeElement !== el) el.value = idx;
  }
  if (stuck) {
    reportMessage('clock', 'Clock change did not take',
      'The Orion refuses sample-rate and clock-source ' +
      'writes while the host is streaming audio over USB, and refuses a rate change while ' +
      'the clock source is <b>USB</b>. On Linux, free the device first:<br>' +
      '<code>systemctl --user stop pipewire pipewire-pulse wireplumber pipewire.socket pipewire-pulse.socket</code><br>' +
      'set the clock to <b>Oven</b>, change the rate, then bring audio back:<br>' +
      '<code>systemctl --user start pipewire pipewire-pulse wireplumber</code>');
  } else clearMessage('clock');
}

$('[data-emm-mic]').addEventListener('change', e => { EMU_MIC = e.target.value; saveEmuMic(); syncEmuModal(); });
$('[data-emm-enable]').addEventListener('click', () => applyEmu(EMM.ch, {on: !emuState(EMM.ch).on}));
$('[data-emm-swap]').addEventListener('click', () => {
  if ($('[data-emm-swap]').disabled) return;
  applyEmu(EMM.ch, {swap: !emuState(EMM.ch).swap});
});
$('[data-emm-model]').addEventListener('change', e => {
  const model = +e.target.value;
  applyEmu(EMM.ch, {model, pattern: emuDefaultPattern(model)});
});
$('[data-emm-pat]').addEventListener('input', e => {
  $('[data-emm-patv]').textContent = emuPatLabel(emuState(EMM.ch).model, +e.target.value);
  applyEmu(EMM.ch, {pattern: +e.target.value}, {throttle: true});
});
