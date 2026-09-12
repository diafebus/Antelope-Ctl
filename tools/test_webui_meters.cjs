// Offline rendering regression checks: node tools/test_webui_meters.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {ROOT: root, JS_FILES, readWebUISource} = require('./webui_sources.cjs');
const html = fs.readFileSync(path.join(root, 'webui/static/index.html'), 'utf8');
const surroundCss = fs.readFileSync(path.join(root, 'webui/static/surround.css'), 'utf8');
const sourceFiles = [...html.matchAll(/<script src="\/webui\/static\/([^"]+)"><\/script>/g)]
  .map(match => match[1].split('?')[0]);
assert.deepEqual(sourceFiles, JS_FILES);
assert.match(html, /<link rel="stylesheet" href="\/webui\/static\/app\.css">/);
assert.match(html, /<link rel="stylesheet" href="\/webui\/static\/surround\.css\?v=[^"]+">/);
assert.match(html, /data-rtab="surround"/);
assert.match(html, /data-rpane="surround"/);
assert.match(surroundCss, /\.surround-eq-grid \{[^}]*repeat\(16,minmax\(0,1fr\)\)/);
assert.match(surroundCss, /\.surround-eq-legend/);
assert.match(surroundCss, /\.surround-eq-reset \{[^}]*flex:0 0 auto;[^}]*width:max-content/);
const js = readWebUISource();
const profile = JSON.parse(fs.readFileSync(path.join(root, 'profiles/orion_studio_sc.json')));
const zenProfile = JSON.parse(fs.readFileSync(path.join(root, 'profiles/zen_go_sc.json')));
const readbackSection = html.slice(html.indexOf('<section id="readbacksec"'), html.indexOf('</section>', html.indexOf('<section id="readbacksec"')) + '</section>'.length);
assert.match(readbackSection, /data-min="readbackbody"[^>]*title="expand this section"[^>]*aria-expanded="false">\+<\/button>/);
assert.match(readbackSection, /class="secbody min" id="readbackbody"/);
assert.match(js, /const saved = localStorage\.getItem\(key\);[\s\S]*saved === '1' \|\| saved === '0'/);
assert.match(js, /selectMixer\(initial, !!routeMix \|\| !!selector \|\| hasSurfaceSelection\)/);
assert.match(js, /function buildSurround\(\)/);
assert.match(js, /const SURROUND_FORMAT_OPTIONS = \[/);
assert.match(js, /function surroundEqGraph\(\w+\)/);
assert.match(js, /const maxGain = 18;/);
assert.match(js, /function surroundEqGrid\(speaker(?:, writable = false)?\)/);
assert.match(js, /function surroundEqSigma\(q\)/);
assert.match(js, /Math\.log2\(band\.frequency\)/);
assert.match(js, /function surroundEqDefaultValue\(input/);
assert.match(js, /input\.addEventListener\('dblclick'/);
assert.match(js, /function requestSurroundEqReset\(button\)/);
assert.match(js, /\/api\/surround\/eq\/reset/);
assert.match(js, /16-band EQ · single view/);
assert.match(js, /class="mixer-knob surround-knob"/);
assert.doesNotMatch(js, /surroundEqTable/);
const source = js.slice(js.indexOf('const METER_FLOOR'), js.indexOf('// ---- buses'));
const mixerSource = js.slice(js.indexOf('function applyMixerMeters'), js.indexOf('function buildMixer'));
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
// Syntax-check every browser-loaded file, including code outside the tested functions.
new vm.Script(js);
const surroundContext = vm.createContext({$: () => null});
vm.runInContext(fs.readFileSync(path.join(root, 'webui/static/ui-surround.js'), 'utf8'),
  surroundContext);
const surroundBands = Array.from({length: 16}, (_, index) => ({
  freq_hz: 30 + index * 100,
  q: 0.71,
  gain_db: index - 8,
  mode: index === 0 ? 0 : 2,
}));
const surroundData = {
  speaker_count: 16,
  speakers: Array.from({length: 16}, (_, index) => ({
    index, label: 'Speaker ' + (index + 1), active: index < 2,
    readback: true, bands: surroundBands,
  })),
  global: {format: '2.0', flags_a_raw: 2, flags_b_raw: 159},
  write: {enabled: false},
};
const surroundHTML = surroundContext.surroundSpeakerHTML(surroundData);
assert.equal((surroundHTML.match(/class="surround-band"/g) || []).length, 16);
assert.equal((surroundHTML.match(/class="mixer-knob surround-knob"/g) || []).length, 48);
assert.equal((surroundHTML.match(/class="surround-eq-mode"/g) || []).length, 16);
assert.match(surroundHTML, /16-band EQ · single view/);
assert.match(surroundHTML, /<strong>1<\/strong>/);
assert.doesNotMatch(surroundHTML, /<strong>BAND /);
assert.match(surroundHTML, /<span>F<\/span><span>G<\/span><span>Q<\/span>/);
assert.equal((surroundHTML.match(/class="mixer-knob-label"/g) || []).length, 0);
assert.ok(surroundContext.surroundEqSigma(10) < surroundContext.surroundEqSigma(0.5));
const graphBands = [
  {freq_hz: 100, q: 10, gain_db: 6, mode: 2},
  {freq_hz: 5000, q: 0.5, gain_db: -3, mode: 2},
];
const curve = surroundContext.surroundEqCurvePoints(graphBands.map((band, index) => ({
  index, frequency: band.freq_hz, q: band.q, gain: band.gain_db,
})));
assert.equal(curve[0].frequency, 20);
assert.equal(curve[curve.length - 1].frequency, 20000);
const graphHTML = surroundContext.surroundEqGraph({bands: graphBands});
assert.match(graphHTML, /Q-shaped gain estimate from readback/);
assert.match(graphHTML, /surround-eq-area" d="M 42 /);
assert.match(graphHTML, / L 948 [^ ]+ L 42 /);
const resetPreset = {
  frequency_hz: [30, 45, 90, 160, 350, 650, 1100, 1700,
    2500, 3500, 4750, 6250, 8250, 10750, 13000, 15000],
  q: 0.71, gain_db: 0,
};
const resetInput = (field, band) => ({
  dataset: {surroundEqField: field, surroundEqBand: String(band)},
});
assert.equal(surroundContext.surroundEqDefaultValue(
  resetInput('frequency', 5), resetPreset), 650);
assert.equal(surroundContext.surroundEqDefaultValue(
  resetInput('q', 5), resetPreset), 0.71);
assert.equal(surroundContext.surroundEqDefaultValue(
  resetInput('gain', 5), resetPreset), 0);
assert.equal(surroundContext.surroundEqDefaultValue(
  resetInput('mode', 5), resetPreset), null);
const writableSurroundHTML = surroundContext.surroundSpeakerHTML({
  ...surroundData, write: {enabled: false, eq: {enabled: true, reset: resetPreset}},
});
assert.match(writableSurroundHTML, /experimental write · one field at a time/);
assert.equal((writableSurroundHTML.match(/data-surround-eq-input/g) || []).length, 64);
assert.doesNotMatch(writableSurroundHTML, /data-surround-eq-input[^>]* disabled/);
assert.equal((writableSurroundHTML.match(/data-surround-eq-reset/g) || []).length, 1);
assert.match(writableSurroundHTML, /data-surround-eq-speaker="0"/);
assert.doesNotMatch(writableSurroundHTML, /data-surround-eq-reset[^>]* disabled/);
const inputsSource = fs.readFileSync(path.join(root, 'webui/static/ui-inputs.js'), 'utf8');
assert.match(inputsSource, /\.replace\(\/\^Preamp\\s\+\/i, 'CH'\)/);
const globalHTML = surroundContext.surroundGlobalHTML(surroundData);
assert.match(globalHTML, /value="2\.0" selected/);
assert.match(globalHTML, /value="9\.1\.6" disabled/);
assert.equal((globalHTML.match(/data-surround-bass-open/g) || []).length, 1);
assert.match(globalHTML, /data-surround-bass-modal/);
assert.match(globalHTML, /Bass Management/);
console.log('WebUI meter rendering checks passed (12 channels, scale, colors, peak hold, missing data).');
