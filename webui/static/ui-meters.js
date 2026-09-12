"use strict";

const METER_DEBUG = new URLSearchParams(location.search).has('meterdebug');
const MDBG_SEEN = {};        // "tag@off" -> Set of values seen, to flag movers
function mdbgGroup(hostId, tag, raw) {
  if (!raw || !raw.bytes) return;
  $('#mdbgsec').hidden = false;
  const host = $('#' + hostId);
  if (host.children.length !== raw.bytes.length) {
    host.innerHTML = raw.bytes.map((_, i) =>
      `<div class="b"><span class="o">@${raw.base + i}</span>`
      + `<span class="v"></span><div class="bar"></div></div>`).join('');
  }
  raw.bytes.forEach((val, i) => {
    const key = tag + '@' + (raw.base + i);
    (MDBG_SEEN[key] || (MDBG_SEEN[key] = new Set())).add(val);
    const b = host.children[i];
    b.querySelector('.v').textContent = val;
    b.querySelector('.bar').style.width = Math.max(0, Math.min(100, (96 - val) / 96 * 100)) + '%';
    b.classList.toggle('move', MDBG_SEEN[key].size > 2);
  });
}
function applyMeterDebug(s) {
  mdbgGroup('mdbg', '75', s.meters_raw);
  mdbgGroup('mdbg73', '73', s.state_raw);
}
// Meter scale: bottom = METER_FLOOR dB, top = 0 dB, expanded toward 0 so a
// couple of dB near clip take much more of the bar than the same span deep
// down (gamma > 1). Both the fill level and the colour-zone gradient stops go
// through this, so they always line up.
// FLOOR is -60 to match the db_curve's floor: a silent channel reads exactly
// -60 dB, which must map to 0% or every strip shows a resting green stub.
const METER_FLOOR = -60, METER_GAMMA = 2;
function dbToPct(db) {
  const x = Math.max(0, (db - METER_FLOOR) / -METER_FLOOR);   // 0..1 linear in dB
  return Math.max(0, Math.min(100, Math.pow(x, METER_GAMMA) * 100));
}
function meterGradient() {
  const g = 'var(--meter)', y = 'var(--warn)', o = 'var(--orange)', r = 'var(--clip)';
  const p12 = dbToPct(-12).toFixed(2), p6 = dbToPct(-6).toFixed(2), p2 = dbToPct(-2).toFixed(2);
  return `linear-gradient(0deg, ${g} ${p12}%, ${y} ${p12}%, ${y} ${p6}%, `
       + `${o} ${p6}%, ${o} ${p2}%, ${r} ${p2}%)`;
}
const CLIP_HOLD_MS = 1500;   // hold after confirmed clip or raw top-of-scale
const CLIP_TIMER = {};
function meterPresentation(sample, spec) {
  const legacyDb = typeof sample === 'number' && Number.isFinite(sample) ? sample : null;
  const db = legacyDb ?? (Number.isFinite(sample?.db) ? sample.db : null);
  const raw = Number.isFinite(sample?.raw) ? sample.raw : null;
  const validRaw = raw != null && raw >= 0 && raw <= 96;
  // Presentation approximation only: restore the earlier -raw visual response
  // for the confirmed Orion physical bank. Never write this estimate into the
  // protocol's db/clip fields or borrow calibration from the 0x75 report.
  const estimated = db == null && validRaw
    && spec?.physical_meter_base_offset === 221
    && spec?.physical_meter_direction === 'inverted'
    && spec?.physical_meter_raw_range?.[0] === 0
    && spec?.physical_meter_raw_range?.[1] === 96;
  const known = db != null || validRaw;
  const silent = sample?.silence === true;
  const pct = silent ? 0 : db != null ? dbToPct(db)
    : estimated ? dbToPct(-raw) : validRaw ? (96 - raw) / 96 * 100 : 0;
  return {
    pct, known, estimated, rawOnly: db == null && validRaw && !estimated,
    peak: known && !silent && (sample?.clip === true || legacyDb != null && legacyDb >= 0
      || estimated && sample?.clip == null && raw === 0),
    title: estimated ? `Raw ${raw}; approximate level/color scale (uncalibrated)`
      : db != null ? `${db.toFixed(1)} dBFS` : validRaw ? `Raw ${raw}` : 'Meter unavailable',
  };
}
function applyMeters(meters) {
  // Visit every strip so truncated/missing samples cannot leave stale peaks.
  for (let ch = 0; ch < N_CH; ch++) {
    const sample = meters?.[ch];
    const bar = document.querySelector(`.pre[data-ch="${ch}"] [data-meter]`); if (!bar) continue;
    const view = meterPresentation(sample, PROFILE?.frame?.state_report);
    bar.classList.toggle('raw', view.rawOnly);
    bar.style.clipPath = `inset(${(100 - view.pct).toFixed(1)}% 0 0 0)`;
    bar.parentElement.title = view.title;
    const led = document.querySelector(`.pre[data-ch="${ch}"] [data-clip]`);
    if (!led) continue;
    led.title = view.estimated
      ? 'Peak: raw top-of-scale (clip unverified) — click to clear'
      : 'Clip — click to clear';
    if (!view.known) {
      clearTimeout(CLIP_TIMER[ch]);
      led.classList.remove('on');
    } else if (view.peak) {
      led.classList.add('on');
      clearTimeout(CLIP_TIMER[ch]);
      CLIP_TIMER[ch] = setTimeout(() => led.classList.remove('on'), CLIP_HOLD_MS);
    }
  }
}

// Zen Go exposes six provisional output lanes in the same 0x73 state report.
// Keep the mapping profile-driven and visibly raw-only; this is not a claim
// that the device's exact post-fader/output stage has been decoded.
function outputMeterMappings() {
  return (PROFILE?.frame?.state_report?.meter_mappings || [])
    .filter(m => m?.target === 'physical_output');
}
function outputMeterMapping(bus, lane) {
  return outputMeterMappings().find(m => Number(m.target_index) === Number(bus)
    && Number(m.lane) === Number(lane));
}
function outputMeterSupported(bus) {
  return outputMeterMappings().some(m => Number(m.target_index) === Number(bus));
}
function outputMeterHTML(bus) {
  if (!outputMeterSupported(bus)) return '';
  return `<div class="output-meter-wrap"><div class="output-meter" data-output-meter="${bus}" title="Output meter unavailable — provisional raw lane mapping">`
    + `<i data-output-meter-lane="0" class="unavailable"></i>`
    + `<i data-output-meter-lane="1" class="unavailable"></i></div>`
    + `<span class="output-meter-label">L&nbsp; R</span></div>`;
}
function applyOutputMeters(meters) {
  const defaultRange = Array.isArray(meters?.raw_range) && meters.raw_range.length === 2
    ? meters.raw_range.map(Number) : [0, 96];
  const outputs = Array.isArray(meters?.outputs) ? meters.outputs : [];
  document.querySelectorAll('[data-output-meter]').forEach(host => {
    const bus = Number(host.dataset.outputMeter);
    const output = outputs.find(item => Number(item.bus) === bus);
    const lanes = output?.lanes || [];
    host.querySelectorAll('[data-output-meter-lane]').forEach(el => {
      const lane = Number(el.dataset.outputMeterLane), sample = lanes[lane];
      const mapping = outputMeterMapping(bus, lane);
      const range = Array.isArray(mapping?.raw_range) && mapping.raw_range.length === 2
        ? mapping.raw_range.map(Number) : defaultRange;
      const rawLo = range[0], rawHi = range[1];
      const direction = String(mapping?.direction || 'inverted').toLowerCase();
      const silenceRaw = Number.isFinite(Number(mapping?.silence_raw))
        ? Number(mapping.silence_raw) : rawHi;
      const raw = Number.isFinite(sample?.raw) ? Number(sample.raw) : null;
      const valid = raw != null && raw >= Math.min(rawLo, rawHi) && raw <= Math.max(rawLo, rawHi);
      const silent = sample?.silence === true || raw === silenceRaw;
      const pct = valid && !silent && rawHi > rawLo ? (direction === 'inverted'
        ? (rawHi - raw) / (rawHi - rawLo) * 100
        : (raw - rawLo) / (rawHi - rawLo) * 100) : 0;
      el.classList.toggle('unavailable', !valid);
      el.classList.toggle('peak', valid && raw === rawLo);
      el.classList.toggle('raw', valid);
      el.style.height = pct.toFixed(1) + '%';
      el.title = !valid ? 'Output meter unavailable'
        : `Raw ${raw}${silent ? ' · silence' : ' · provisional / uncalibrated'}`;
    });
    host.title = output
      ? `${output.label || output.name || 'Output'} meter — provisional raw lane mapping`
      : 'Output meter unavailable — provisional raw lane mapping';
  });
}
