// Offline rendering regression checks: node tools/test_webui_meters.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'webui/static/index.html'), 'utf8');
const profile = JSON.parse(fs.readFileSync(path.join(root, 'profiles/orion_studio_sc.json')));
const zenProfile = JSON.parse(fs.readFileSync(path.join(root, 'profiles/zen_go_sc.json')));
const readbackSection = html.slice(html.indexOf('<section id="readbacksec"'), html.indexOf('</section>', html.indexOf('<section id="readbacksec"')) + '</section>'.length);
assert.match(readbackSection, /data-min="readbackbody"[^>]*title="expand this section"[^>]*aria-expanded="false">\+<\/button>/);
assert.match(readbackSection, /class="secbody min" id="readbackbody"/);
assert.match(html, /const saved = localStorage\.getItem\(key\);[\s\S]*saved === '1' \|\| saved === '0'/);
assert.match(html, /selectMixer\(initial, !!routeMix \|\| !!selector \|\| hasSurfaceSelection\)/);
const source = html.slice(html.indexOf('const METER_FLOOR'), html.indexOf('// ---- buses'));
const mixerSource = html.slice(html.indexOf('function applyMixerMeters'), html.indexOf('function buildMixer'));
const classes = () => {
  const values = new Set();
  return { add: x => values.add(x), remove: x => values.delete(x),
    contains: x => values.has(x), toggle: (x, on) => on ? values.add(x) : values.delete(x) };
};
const bars = Array.from({length: 12}, () => ({classList: classes(), style: {}, parentElement: {}}));
const leds = Array.from({length: 12}, () => ({classList: classes()}));
const mixerPane = {dataset: {mixPane: '0'}};
const mixerBars = [1, 2].map(ch => {
  const meter = {classList: classes(), style: {}, parentElement: {}};
  const strip = {
    dataset: {ch: String(ch)},
    closest: () => mixerPane,
    querySelector: selector => selector === '[data-mix-meter]' ? meter : null,
  };
  return {meter, strip};
});
let nextTimer = 0;
const timers = new Map();
const context = vm.createContext({PROFILE: profile, N_CH: 12,
  mixerHasMaster: () => true,
  document: {querySelector: selector => {
    const ch = Number(selector.match(/data-ch="(\d+)"/)[1]);
    return selector.includes('data-meter') ? bars[ch] : leds[ch];
  }, querySelectorAll: selector => selector.startsWith('#mixer')
    ? mixerBars.map(item => item.strip) : []},
  setTimeout: fn => { timers.set(++nextTimer, fn); return nextTimer; },
  clearTimeout: id => timers.delete(id),
});
vm.runInContext(source, context);
const spec = profile.frame.state_report;
const sample = raw => ({raw, db: null, clip: null, silence: raw === 96});
const view = raw => context.meterPresentation(sample(raw), spec);
assert.equal(spec.channel_meter_base_offset, 221);
assert.equal(view(96).pct, 0);
assert.equal(view(60).pct, 0);
assert.equal(view(30).pct, 25); // restored response, previously 68.75% linear raw
assert.equal(view(12).pct, context.dbToPct(-12)); // fill and gradient share scale
assert.equal(view(6).pct, context.dbToPct(-6));
assert.equal(view(2).pct, context.dbToPct(-2));
assert.equal(view(0).pct, 100);
assert.equal(view(0).peak, true);
assert.equal(view(1).peak, false);
assert.equal(view(12).rawOnly, false);
assert.match(view(12).title, /uncalibrated/);
assert.equal(context.meterPresentation(sample(12), {}).rawOnly, true);
assert.equal(context.meterPresentation({raw: 0, db: -20, clip: false}, spec).peak, false);
assert.equal(context.meterPresentation(0, spec).peak, true); // legacy calibrated input
for (const invalid of [null, undefined, NaN, {raw: NaN}, {raw: -1}, {raw: 97}]) {
  const result = context.meterPresentation(invalid, spec);
  assert.equal(result.pct, 0);
  assert.equal(result.peak, false);
}
const samples = Array.from({length: 12}, () => sample(96));
samples[0] = sample(0); samples[11] = sample(12);
context.applyMeters(samples);
assert.equal(bars[0].style.clipPath, 'inset(0.0% 0 0 0)');
assert.equal(bars[11].classList.contains('raw'), false);
assert.equal(leds[0].classList.contains('on'), true);
assert.match(leds[0].title, /clip unverified/);
context.applyMeters(Array.from({length: 12}, () => sample(96)));
assert.equal(leds[0].classList.contains('on'), true); // holds through silence
for (const expire of [...timers.values()]) expire();
assert.equal(leds[0].classList.contains('on'), false);
context.applyMeters(samples);
context.applyMeters([]);
assert.equal(leds[0].classList.contains('on'), false);
assert.equal(bars[11].style.clipPath, 'inset(100.0% 0 0 0)');
assert.equal(timers.size, 0);
vm.runInContext(mixerSource, context);
context.applyMixerMeters({mix: 0, strips: [
  {ch: 1, raw: 24, silence: false},
  {ch: 2, raw: 96, silence: true},
], raw_range: [0, 96], silence_raw: 96, noise_floor_raw: null});
assert.equal(mixerBars[0].meter.style.height, '75.0%');
assert.equal(mixerBars[0].meter.classList.contains('unavailable'), false);
assert.match(mixerBars[0].meter.parentElement.title, /uncalibrated/);
assert.equal(mixerBars[1].meter.style.height, '0.0%');
context.applyMixerMeters({mix: 0, strips: [{ch: 1, raw: 84, silence: false}],
  raw_range: [0, 96], silence_raw: 96, noise_floor_raw: 84});
assert.equal(mixerBars[0].meter.style.height, '0.0%');
assert.match(mixerBars[0].meter.parentElement.title, /noise floor/);
context.PROFILE = zenProfile;
assert.equal(context.outputMeterMappings().length, 6);
assert.equal(context.outputMeterSupported(0), true);
assert.equal(context.outputMeterSupported(3), false);
assert.equal(context.outputMeterMapping(1, 1).payload_offset, '0xdd');
assert.match(context.outputMeterHTML(2), /data-output-meter-lane="1"/);
// Syntax-check every inline script, including code outside the tested functions.
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
  new vm.Script(match[1]);
}
console.log('WebUI meter rendering checks passed (12 channels, scale, colors, peak hold, missing data).');
