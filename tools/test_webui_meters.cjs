// Offline rendering regression checks: node tools/test_webui_meters.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {ROOT: root, JS_FILES, readWebUISource} = require('./webui_sources.cjs');
const html = fs.readFileSync(path.join(root, 'webui/static/index.html'), 'utf8');
const surroundCss = fs.readFileSync(path.join(root, 'webui/static/surround.css'), 'utf8');
const busSource = fs.readFileSync(path.join(root, 'webui/static/ui/buses.js'), 'utf8');
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
assert.match(surroundCss, /\.surround-eq-number-row/);
assert.match(surroundCss, /\.surround-eq-unit/);
assert.match(surroundCss, /\.surround-global-body \{ display:grid; grid-template-columns:minmax\(0,1fr\) minmax\(310px,.8fr\)/);
assert.match(surroundCss, /\.surround-global-controlbox \{ display:grid; grid-template-rows:auto auto auto/);
assert.match(surroundCss, /\.surround-speaker-button-group \{ display:grid; grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
assert.match(surroundCss, /\.surround-speaker-map \{ display:grid; grid-template-columns:repeat\(8,minmax\(42px,1fr\)\)/);
assert.match(surroundCss, /\.surround-speaker-node\.selected \{[^}]*box-shadow:/);
assert.match(surroundCss, /\.bass-fader-number \{ border:1px solid var\(--accent\)/);
assert.match(surroundCss, /\.surround-monitor-dial \{ width:42px; height:42px/);
assert.match(surroundCss, /\.surround-speaker-toggle\.on \{[^}]*box-shadow:/);
assert.match(surroundCss, /\.surround-bass-open \{ flex:0 0 auto; width:auto; min-width:50px/);
assert.match(surroundCss, /\.bass-board \{/);
assert.match(surroundCss, /\.bass-group-lfe \{[^}]*--bass-color/);
assert.match(surroundCss, /\.bass-strip::before/);
assert.match(surroundCss, /\.bass-order-control/);
assert.match(surroundCss, /grid-template-columns:var\(--bass-rail-width\) repeat\(var\(--bass-count\),var\(--bass-strip-width\)\)/);
assert.match(surroundCss, /--bass-strip-width:64px/);
assert.match(surroundCss, /\.bass-knob \{[^}]*width:32px; height:32px/);
assert.match(surroundCss, /\.bass-knob-control \.mixer-readout \{[^}]*min-width:0/);
assert.match(surroundCss, /\.bass-knob input:disabled \{[^}]*opacity:0/);
assert.doesNotMatch(surroundCss, /\.bass-knob input:disabled, \.bass-order-control/);
assert.match(surroundCss, /\.surround-eq-mode-button \{/);
assert.match(surroundCss, /\.surround-eq-mode-button img \{/);
assert.match(surroundCss, /\.bass-popup-body \{/);
assert.match(surroundCss, /\.surround-bass-popup-page \{/);
assert.match(busSource, /raw 0 = 0 dB \(maximum\/unity\)/);
assert.match(busSource, /raw 1\.\.95 = -N dB, and raw 96 = -∞ \(silent\)/);
assert.match(busSource, /value="\$\{96 - b\.level\}"/);
assert.match(busSource, /post\('\/api\/bus', \{bus: b\.bus, level: 96 - \+e\.target\.value\}\)/);
assert.match(busSource, /const frac = Math\.max\(0, Math\.min\(1, \(96 - level\) \/ 96\)\)/);
assert.match(busSource, /Raw values are used directly for labels and writes/);
assert.match(busSource, /live = startAtt \+ \(e\.clientY - startY\)/);
assert.match(busSource, /live = curAtt\(\) \+ Math\.sign\(e\.deltaY\)/);
const busLabelContext = vm.createContext({});
vm.runInContext(busSource.slice(0, busSource.indexOf('// Monitor A')), busLabelContext);
assert.equal(vm.runInContext('busLevelLabel(0)', busLabelContext), '0 dB');
assert.equal(vm.runInContext('busLevelLabel(48)', busLabelContext), '−48 dB');
assert.equal(vm.runInContext('busLevelLabel(96)', busLabelContext), '−∞');
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
assert.match(js, /function surroundEqGraph\(\w+, writable = false\)/);
assert.match(js, /const maxGain = 18;/);
assert.match(js, /function surroundEqGrid\(speaker(?:, writable = false)?\)/);
assert.match(js, /function surroundEqSigma\(q\)/);
assert.match(js, /Math\.log2\(band\.frequency\)/);
assert.match(js, /function surroundEqDefaultValue\(input/);
assert.match(js, /data-surround-eq-number/);
assert.match(js, /function surroundEqSnap\(value/);
assert.match(js, /function postSurroundEqInput\(input\)/);
assert.match(js, /function initSurroundEqGraphControls\(host\)/);
assert.match(js, /data-surround-eq-point/);
assert.match(js, /\/api\/surround\/eq\/point/);
assert.match(js, /wheel over a point adjusts Q/);
assert.match(js, /wheelRemainder/);
assert.match(js, /wheelCommitTimer/);
assert.match(js, /function surroundSpeakerHeadControl\(/);
assert.match(js, /function surroundSpeakerBypassControl\(/);
assert.match(js, /function surroundSpeakerOverview\(data\)/);
assert.match(js, /data-surround-speaker-select/);
assert.match(js, /class="mixer-knob surround-monitor-dial"/);
assert.match(js, /class="btn surround-bass-open"/);
assert.match(js, /function beginSurroundBassFaderEdit\(readout\)/);
assert.match(js, /data-bass-fader-number/);
assert.match(js, /const trackHandle = 20/);
assert.match(js, /art\.style\.top/);
assert.match(js, /data-surround-speaker-head-toggle/);
assert.match(js, /\/api\/surround\/speaker/);
assert.match(js, /input\.dataset\.surroundSpeakerHeadField !== 'level_db'[\s\S]*input\.value = '0'[\s\S]*dispatchEvent\(new Event\('change'/);
assert.match(js, /function initSurroundGlobalControls\(host\)[\s\S]*wirePrecisionRange\(input\)/);
assert.match(js, /data-precision-drag-pixels="\$\{field === 'level_db' \? 760 : 40\}"/);
assert.match(js, /data-precision-drag-pixels="\$\{field === 'level_db' \? 760 : 1000\}"/);
const speakerHeadInitStart = js.indexOf('function initSurroundSpeakerHeadControls');
const speakerHeadInitEnd = js.indexOf('function postSurroundSpeakerHeadInput', speakerHeadInitStart);
assert.ok(speakerHeadInitStart >= 0 && speakerHeadInitEnd > speakerHeadInitStart);
assert.match(js.slice(speakerHeadInitStart, speakerHeadInitEnd), /wirePrecisionRange\(input\)/);
assert.match(js, /function openSurroundBassWindow\(\)/);
assert.match(js, /window\.open\('', 'antelopeBassManagement'/);
assert.match(js, /surround\.css\?v=surround-controls-v11/);
assert.match(js, /addEventListener\('load', repaintFaders/);
assert.match(js, /data-logarithmic="true"/);
assert.match(js, /Math\.exp\(Math\.log\(value\)/);
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
vm.runInContext(fs.readFileSync(path.join(root, 'webui/static/ui/surround.js'), 'utf8'),
  surroundContext);
const surroundBands = Array.from({length: 16}, (_, index) => ({
  freq_hz: 30 + index * 100,
  q: 0.71,
  gain_db: index - 8,
  mode: index === 0 ? 0 : index === 15 ? 1 : 2,
}));
const surroundData = {
  speaker_count: 16,
  speakers: Array.from({length: 16}, (_, index) => ({
    index, label: 'Speaker ' + (index + 1), active: index < 2,
    readback: true, head_readback: true,
    head: {delay_ms: 0.6, level_db: 0, phase_invert: false},
    bypass: false, bypass_readback: true, bands: surroundBands,
  })),
  global: {format: '2.0', flags_a_raw: 2, flags_b_raw: 159},
  write: {enabled: false},
};
const surroundHTML = surroundContext.surroundSpeakerHTML(surroundData);
assert.equal((surroundHTML.match(/class="surround-band"/g) || []).length, 16);
assert.equal((surroundHTML.match(/class="mixer-knob surround-knob"/g) || []).length, 48);
assert.equal((surroundHTML.match(/class="surround-eq-mode"/g) || []).length, 16);
assert.equal((surroundHTML.match(/class="surround-eq-mode-button"/g) || []).length, 16);
assert.equal((surroundHTML.match(/srrndeq-bttn-bg\.svg/g) || []).length, 16);
assert.match(surroundHTML, /srrndeq-bttn-lshelvingdown\.svg/);
assert.match(surroundHTML, /srrndeq-bttn-hshelvingup\.svg/);
assert.match(surroundHTML, /srrndeq-bttn-belldown\.svg/);
assert.match(surroundHTML, /srrndeq-bttn-flat\.svg/);
assert.match(surroundHTML, /srrndeq-bttn-bellup\.svg/);
assert.match(surroundHTML, /16-band EQ · single view/);
assert.match(surroundHTML, /class="surround-speaker-button-group"[\s\S]*Phase invert[\s\S]*Bypass processing/);
assert.match(surroundHTML, /class="surround-eq-actions"[\s\S]*data-surround-eq-reset/);
assert.doesNotMatch(surroundHTML, /data-surround-speaker>/);
assert.match(surroundHTML, /<strong>1<\/strong>/);
assert.doesNotMatch(surroundHTML, /<strong>BAND /);
assert.match(surroundHTML, /<span>F<\/span><span>G<\/span><span>Q<\/span>/);
assert.doesNotMatch(surroundHTML, /data-surround-eq-field="mode"/);
assert.equal((surroundHTML.match(/class="mixer-knob-label"/g) || []).length, 0);
assert.equal(surroundContext.surroundEqStateName(-1, 0, 0), 'lshelvingdown');
assert.equal(surroundContext.surroundEqStateName(1, 0, 0), 'lshelvingup');
assert.equal(surroundContext.surroundEqStateName(0, 0, 4), 'hpf');
assert.equal(surroundContext.surroundEqStateName(-1, 15, 1), 'hshelvingdown');
assert.equal(surroundContext.surroundEqStateName(1, 15, 1), 'hshelvingup');
assert.equal(surroundContext.surroundEqStateName(0, 15, 3), 'lpf');
assert.equal(surroundContext.surroundEqStateName(-1, 4, 2), 'belldown');
assert.equal(surroundContext.surroundEqStateName(0, 4, 2), 'flat');
assert.equal(surroundContext.surroundEqStateName(1, 4, 2), 'bellup');
assert.equal(surroundContext.surroundEqStateName(-1, 0, 2), 'belldown');
assert.equal(surroundContext.surroundEqModeValues(2, 0).join(','), '2');
assert.ok(surroundContext.surroundEqSigma(10) < surroundContext.surroundEqSigma(0.5));
const lowShelf = [{index: 0, frequency: 100, q: 0.71, gain: 6, mode: 0}];
const highShelf = [{index: 15, frequency: 1000, q: 0.71, gain: 6, mode: 1}];
const highPass = [{index: 0, frequency: 1000, q: 0.71, gain: 0, mode: 4}];
const lowPass = [{index: 15, frequency: 1000, q: 0.71, gain: 0, mode: 3}];
assert.ok(surroundContext.surroundEqResponseAt(lowShelf, 20)
  > surroundContext.surroundEqResponseAt(lowShelf, 2000));
assert.ok(surroundContext.surroundEqResponseAt(highShelf, 20000)
  > surroundContext.surroundEqResponseAt(highShelf, 20));
assert.ok(surroundContext.surroundEqResponseAt(highPass, 20)
  < surroundContext.surroundEqResponseAt(highPass, 20000));
assert.ok(surroundContext.surroundEqResponseAt(lowPass, 20)
  > surroundContext.surroundEqResponseAt(lowPass, 20000));
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
assert.match(graphHTML, /Approximate EQ response from readback/);
assert.match(graphHTML, /surround-eq-area" d="M 42 /);
assert.match(graphHTML, / L 948 [^ ]+ L 42 /);
const writableGraphHTML = surroundContext.surroundEqGraph({index: 0, bands: graphBands}, true);
assert.equal((writableGraphHTML.match(/data-surround-eq-point/g) || []).length, 2);
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
assert.equal(surroundContext.surroundEqSnap(34.4, 20, 20000, 1), 34);
assert.equal(surroundContext.surroundEqSnap(40.006, 20, 20000, 1), 40);
assert.equal(surroundContext.surroundEqSnap(-1, 20, 20000, 1), 20);
const writableSurroundHTML = surroundContext.surroundSpeakerHTML({
  ...surroundData, write: {enabled: false, eq: {enabled: true, reset: resetPreset}},
});
assert.match(writableSurroundHTML, /writable · drag writes frequency \+ gain/);
assert.equal((writableSurroundHTML.match(/data-surround-eq-input/g) || []).length, 48);
assert.equal((writableSurroundHTML.match(/class="mixer-readout surround-eq-number"/g) || []).length, 48);
assert.equal((writableSurroundHTML.match(/data-surround-eq-number/g) || []).length, 48);
assert.equal((writableSurroundHTML.match(/data-surround-eq-mode/g) || []).length, 48);
assert.equal((writableSurroundHTML.match(/class="surround-eq-mode-button"[^>]* disabled/g) || []).length, 14);
assert.doesNotMatch(writableSurroundHTML, /data-surround-eq-input[^>]* disabled/);
assert.doesNotMatch(writableSurroundHTML, /data-surround-eq-number[^>]* disabled/);
assert.equal((writableSurroundHTML.match(/data-surround-eq-reset/g) || []).length, 1);
assert.match(writableSurroundHTML, /data-surround-eq-speaker="0"/);
assert.doesNotMatch(writableSurroundHTML, /data-surround-eq-reset[^>]* disabled/);
const writableHeadHTML = surroundContext.surroundSpeakerHTML({
  ...surroundData,
  speakers: surroundData.speakers.map(speaker => ({
    ...speaker,
    head_readback: true,
    head: {delay_ms: 0.6, level_db: 0, phase_invert: false},
  })),
  write: {
    speaker_head: {
      enabled: true,
      experimental: false,
      fields: ['delay_ms', 'level_db', 'phase_invert'],
      controls: {
        delay_ms: {range: [0.6, 100.6], step: 0.1, unit: 'ms', digits: 1},
        level_db: {range: [-60, 16], step: 0.1, unit: 'dB', digits: 1},
        phase_invert: {boolean: true},
      },
    },
    speaker_bypass: {
      enabled: true, experimental: false, fields: ['bypass'],
    },
  },
});
assert.match(writableHeadHTML, /data-surround-speaker-head-field="delay_ms"/);
assert.match(writableHeadHTML, /data-surround-speaker-head-field="level_db"/);
assert.doesNotMatch(writableHeadHTML, /data-surround-speaker-head-field="delay_ms"[^>]* disabled/);
assert.doesNotMatch(writableHeadHTML, /data-surround-speaker-head-field="level_db"[^>]* disabled/);
assert.match(writableHeadHTML, /data-surround-speaker-head-field="delay_ms"[^>]*min="0.6" max="100.6"/);
assert.match(writableHeadHTML, /data-surround-speaker-head-field="level_db"[^>]*min="-60" max="16"/);
assert.match(writableHeadHTML, /Phase invert/);
assert.match(writableHeadHTML, /data-surround-speaker-head-toggle/);
assert.doesNotMatch(writableHeadHTML, /data-surround-speaker-head-toggle[^>]* disabled/);
assert.match(writableHeadHTML, /Bypass processing/);
assert.match(writableHeadHTML, /data-surround-speaker-bypass/);
assert.doesNotMatch(writableHeadHTML, /data-surround-speaker-bypass[^>]* disabled/);
const inputsSource = fs.readFileSync(path.join(root, 'webui/static/ui/inputs.js'), 'utf8');
assert.match(inputsSource, /\.replace\(\/\^Preamp\\s\+\/i, 'CH'\)/);
const globalHTML = surroundContext.surroundGlobalHTML(surroundData);
assert.match(globalHTML, /value="2\.0" selected/);
assert.match(globalHTML, /value="9\.1\.6" disabled/);
assert.equal((globalHTML.match(/data-surround-bass-open/g) || []).length, 1);
assert.doesNotMatch(globalHTML, /data-surround-bass-modal/);
assert.match(globalHTML, /Bass management/);
assert.match(globalHTML, /class="surround-global-controlbox"[\s\S]*data-surround-bass-open/);
assert.equal((globalHTML.match(/data-surround-speaker-select/g) || []).length, 16);
assert.match(globalHTML, /surround-speaker-node selected/);
assert.match(globalHTML, /B bypass · M mute · D dim/);
const bass20HTML = surroundContext.surroundBassPopupHTML(surroundData);
assert.match(bass20HTML, /class="surround-bass-popup-page"/);
assert.equal((bass20HTML.match(/class="surround-bass-dialog"/g) || []).length, 1);
assert.equal((bass20HTML.match(/class="bass-strip /g) || []).length, 2);
assert.match(bass20HTML, /style="--bass-count:2"/);
assert.match(bass20HTML, /data-bass-channel="1"/);
assert.match(bass20HTML, /data-bass-channel="3"/);
const bass51HTML = surroundContext.surroundBassPopupHTML({
  ...surroundData,
  global: {...surroundData.global, format: '5.1'},
});
assert.equal((bass51HTML.match(/class="bass-strip /g) || []).length, 6);
assert.match(bass51HTML, /style="--bass-count:6"/);
assert.ok(bass51HTML.indexOf('data-bass-channel="4"')
  < bass51HTML.indexOf('data-bass-channel="1"'));
assert.match(bass51HTML, /class="bass-strip bass-group-lfe" data-bass-channel="4"/);
assert.match(bass20HTML, /data-bass-field="lp_cutoff_hz"[^>]* disabled/);
const writableBassData = {
  ...surroundData,
  global: {
    ...surroundData.global,
    format: '2.1',
    bass_mgmt_filter_types: {hp: 'Linkwitz-Riley', lp: 'Butterworth'},
    bass_mgmt_channels: [
      {lp_cutoff_hz: 80, hp_cutoff_hz: 80, lp_order: 0, hp_order: 0,
        fader_db: 0, fader_mute: false},
      {lp_cutoff_hz: 90, hp_cutoff_hz: 90, lp_order: 1, hp_order: 1,
        fader_db: -3, fader_mute: true},
      {lp_cutoff_hz: 100, hp_cutoff_hz: 100, lp_order: 2, hp_order: 2,
        fader_db: 3, fader_mute: false},
    ],
  },
  write: {
    enabled: false,
    bass: {
      enabled: true,
      experimental: false,
      fader_range_db: [-60, 16],
      fields: ['lp_cutoff_hz', 'hp_cutoff_hz', 'lp_bypass', 'hp_bypass',
        'lp_order', 'hp_order', 'fader_db', 'fader_mute',
        'fader_solo', 'hp_filter_type', 'lp_filter_type',
        'link_hp_cutoff', 'link_hp_filter_type', 'link_hp_order',
        'link_hp_bypass', 'link_lp_cutoff', 'link_lp_filter_type',
        'link_lp_order', 'link_lp_bypass', 'link_mixer'],
      filter_type_values: {
        hp_filter_type: [
          {value: 'Butterworth', label: 'Butterworth'},
          {value: 'Linkwitz-Riley', label: 'Linkwitz-Riley'},
        ],
        lp_filter_type: [
          {value: 'Butterworth', label: 'Butterworth'},
          {value: 'Linkwitz-Riley', label: 'Linkwitz-Riley'},
        ],
      },
      link_fields: ['link_hp_cutoff', 'link_hp_filter_type', 'link_hp_order',
        'link_hp_bypass', 'link_lp_cutoff', 'link_lp_filter_type',
        'link_lp_order', 'link_lp_bypass', 'link_mixer'],
      block_count: 3,
      note: 'known Bass Management fields',
    },
  },
};
const writableBassHTML = surroundContext.surroundBassPopupHTML(writableBassData);
assert.equal((writableBassHTML.match(/class="bass-strip /g) || []).length, 3);
assert.match(writableBassHTML, /data-bass-field="lp_cutoff_hz"/);
assert.doesNotMatch(writableBassHTML, /data-bass-field="lp_cutoff_hz"[^>]* disabled/);
assert.match(writableBassHTML, /data-bass-field="fader_db"/);
assert.match(writableBassHTML, /data-bass-field="fader_db"[^>]*min="-60" max="16" step="0.1" value="0"/);
assert.match(writableBassHTML, /data-bass-field="fader_db"[^>]*min="-60" max="16" step="0.1" value="-3"/);
assert.match(writableBassHTML, /data-bass-field="fader_db"[^>]*min="-60" max="16" step="0.1" value="3"/);
assert.match(writableBassHTML, /data-bass-field="fader_mute"/);
assert.match(writableBassHTML, /class="bass-chip bass-order-control"/);
assert.match(writableBassHTML, /class="bass-chip bass-filter-type"/);
assert.match(writableBassHTML, /<option value="Linkwitz-Riley" selected>Linkwitz-Riley<\/option>/);
assert.doesNotMatch(writableBassHTML, /data-bass-filter-type="true"[^>]* disabled/);
assert.match(writableBassHTML, /read\/write/);
assert.match(writableBassHTML, /filter type, link, and solo confirmed by readback/);
assert.ok(writableBassHTML.indexOf('data-bass-channel="4"')
  > writableBassHTML.indexOf('data-bass-channel="1"'));
assert.equal((writableBassHTML.match(/class="bass-link"/g) || []).length, 9);
assert.doesNotMatch(writableBassHTML, /class="bass-link"[^>]* disabled/);
assert.match(writableBassHTML, /data-bass-field="fader_solo"/);
assert.doesNotMatch(writableBassHTML, /data-bass-field="fader_solo"[^>]* disabled/);
const writableBass20Data = {
  ...surroundData,
  global: {
    ...surroundData.global,
    format: '2.0',
    bass_mgmt_channels: [
      {lp_cutoff_hz: 80, hp_cutoff_hz: 80, lp_order: 0, hp_order: 0,
        fader_db: 0, fader_mute: false},
      {lp_cutoff_hz: 90, hp_cutoff_hz: 90, lp_order: 1, hp_order: 1,
        fader_db: -3, fader_mute: true},
    ],
  },
  write: {
    enabled: false,
    bass: {
      enabled: true,
      experimental: false,
      fader_range_db: [-60, 16],
      fields: ['lp_cutoff_hz', 'hp_cutoff_hz', 'lp_bypass', 'hp_bypass',
        'lp_order', 'hp_order', 'fader_db', 'fader_mute',
        'fader_solo', 'hp_filter_type', 'lp_filter_type'],
      filter_type_values: {
        hp_filter_type: ['Butterworth', 'Linkwitz-Riley'],
        lp_filter_type: ['Butterworth', 'Linkwitz-Riley'],
      },
      block_count: 3,
    },
  },
};
const writableBass20HTML = surroundContext.surroundBassPopupHTML(writableBass20Data);
assert.match(writableBass20HTML, /2\.0 · 2 strips/);
assert.doesNotMatch(writableBass20HTML, /data-bass-field="lp_cutoff_hz"[^>]* disabled/);
assert.match(writableBass20HTML, /data-bass-fader[^>]*data-precision-drag-pixels="760"/);
assert.match(writableBass20HTML, /data-bass-fader-number/);
assert.match(writableBass20HTML, /data-bass-field="hp_filter_type"/);
assert.match(writableBass20HTML, /data-bass-field="lp_filter_type"/);
assert.equal(surroundContext.surroundBassInputValue({
  dataset: {bassField: 'fader_db'}, value: '3.5',
}), 3.5);
assert.equal(surroundContext.surroundBassFaderSnap('3.46', {
  min: '-60', max: '16', step: '0.1',
}), 3.5);
assert.equal(surroundContext.surroundBassInputValue({
  dataset: {bassField: 'hp_filter_type', bassFilterType: 'true'},
  value: 'Linkwitz-Riley',
}), 'Linkwitz-Riley');
assert.ok(surroundContext.surroundBassFaderFraction(-3)
  > surroundContext.surroundBassFaderFraction(0));
assert.ok(surroundContext.surroundBassFaderFraction(3)
  < surroundContext.surroundBassFaderFraction(0));
const bassFaderStyle = {};
const bassFaderThumb = {style: {setProperty: (name, value) => {
  bassFaderStyle[name] = value;
}}};
const bassFaderInput = {min: '-60', max: '16', clientHeight: 114};
const bassFaderStrip = {querySelector: selector => {
  if (selector === '[data-bass-fader]') return bassFaderInput;
  if (selector === '.mixer-fader-thumb') return bassFaderThumb;
  if (selector === '.bass-fader-row .mixer-fader-well') return {clientHeight: 122};
  return null;
}};
surroundContext.paintSurroundBassFader(bassFaderStrip, -60);
assert.equal(bassFaderStyle['--fader-pos'], '104.0px');
const stable20 = surroundContext.surroundBassChannels({
  ...writableBass20Data,
  global: {
    ...writableBass20Data.global,
    bass_mgmt_channels: [
      {channel_id: 3, slot: 1, fader_db: -3},
      {channel_id: 1, slot: 0, fader_db: 4},
    ],
  },
});
assert.equal(JSON.stringify(stable20.map(channel => [channel.channelId, channel.slot,
  channel.block.fader_db])), JSON.stringify([[1, 0, 4], [3, 1, -3]]));
const writableGlobalHTML = surroundContext.surroundGlobalHTML({
  ...surroundData,
  write: {
    enabled: false,
    format: {
      enabled: true,
      options: [
        {name: '2.0', writable: true},
        {name: '2.1', writable: true},
        {name: '3.0', writable: false},
      ],
    },
    eq_position: {
      enabled: true,
      experimental: false,
      fields: ['pre', 'post'],
      note: 'EQ position is writable',
    },
  },
});
assert.match(writableGlobalHTML, /data-surround-format/);
assert.doesNotMatch(writableGlobalHTML, /<select data-surround-format[^>]*disabled/);
assert.match(writableGlobalHTML, /value="2\.0" selected/);
assert.match(writableGlobalHTML, /data-surround-eq-position/);
assert.doesNotMatch(writableGlobalHTML, /data-surround-eq-position[^>]* disabled/);
assert.match(writableGlobalHTML, /EQ position is writable/);
assert.match(writableGlobalHTML, /value="3\.0" disabled/);
console.log('WebUI meter rendering checks passed (12 channels, scale, colors, peak hold, missing data).');
