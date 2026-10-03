// Capture-backed panel membership and disabled live gestures, no device access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {ROOT} = require('./webui_sources.cjs');
const fixture = JSON.parse(fs.readFileSync(path.join(ROOT, 'tools/fixtures/afx_modulation_presentations.json')));
const ctx = vm.createContext({
  document: {getElementById: () => ({addEventListener() {}})},
  window: {addEventListener() {}},
  PROFILE: JSON.parse(fs.readFileSync(path.join(ROOT, 'profiles/orion_studio_sc.json'))),
  setTimeout, clearTimeout,
  fetch() { throw new Error('No panel gesture may send a device request in this test'); },
});
for (const name of ['afx', 'afx-controls', 'afx-memorycat', 'afx-v12', 'afx-bbd', 'afx-test', 'afx-live'])
  vm.runInContext(fs.readFileSync(path.join(ROOT, `webui/static/ui/${name}.js`), 'utf8'), ctx);
ctx.fixture = fixture;
vm.runInContext('afxPanelPositionHTML = () => "";', ctx);
for (const effect of fixture.effects) {
  ctx.effect = effect;
  const rendered = vm.runInContext(`AFX_PANELS.get(effect.id).render({live:true,parameterAvailable:false,instance:1,effect,
    values:Object.fromEntries(effect.controls.map(c=>[c.id,null]))},0)`, ctx);
  assert.match(rendered, /Device settings unknown/);
  const inputs = [...rendered.matchAll(/<input[^>]+>/g)].map(m=>m[0]);
  assert.equal(inputs.length, effect.id === 'turboensembler' ? 10 : 4);
  assert.ok(inputs.every(input=>/ disabled/.test(input)));
  assert.doesNotMatch(rendered, /data-afx-control="(presetIndex|peakmeter|bypass)"/);
  const modeButtons = [...rendered.matchAll(/<button[^>]+data-afx-mode[^>]+>/g)].map(m=>m[0]);
  assert.ok(modeButtons.every(button=>/ disabled/.test(button)));
  assert.ok(modeButtons.every(button=>/aria-pressed="false"/.test(button)));
  vm.runInContext(`draft={live:true,parameterAvailable:false,effect,values:{}};
    afxEffectInput(draft,{dataset:{afxControl:'gain'},value:'255'});
    afxLiveChanged({...draft,parameterAvailable:true,instance:0});`, ctx);
  assert.equal(vm.runInContext('Object.keys(draft.values).length', ctx), 0);
  assert.equal(vm.runInContext('AFX_LIVE_PENDING.size', ctx), 0);
}
ctx.effect = fixture.effects.find(e=>e.id === 'turboensembler');
vm.runInContext(`draft={live:false,effect,values:Object.fromEntries(effect.controls.map(c=>[c.id,c.kind==='continuous'?c.range[0]:null]))};`,ctx);
const properties = {}, output = {};
const input = {dataset:{afxControl:'gain',afxSlot:'0'},value:'255',closest:()=>({style:{setProperty:(k,v)=>properties[k]=v},querySelector:()=>output})};
ctx.input = input;
vm.runInContext('afxEffectInput(draft,input)',ctx);
assert.equal(vm.runInContext('draft.values.gain',ctx),255);
assert.equal(properties['--afx-turn'],'135deg');
input.value='256';vm.runInContext('afxEffectInput(draft,input)',ctx);
assert.equal(vm.runInContext('draft.values.gain',ctx),255);
const v12 = vm.runInContext('AFX_PANELS.get(effect.id).render(draft,0)',ctx);
assert.match(v12, /<input(?=[^>]*data-afx-control="color")[^>]* disabled/);
vm.runInContext('draft.values.space=1',ctx);
const enabled = vm.runInContext('AFX_PANELS.get(effect.id).render(draft,0)',ctx);
assert.doesNotMatch(enabled, /<input(?=[^>]*data-afx-control="color")[^>]* disabled/);
assert.equal(vm.runInContext("afxEffectDisplayValue(effect.controls.find(c=>c.id==='pan'),90)",ctx),'0');
assert.equal(vm.runInContext("afxEffectDisplayValue(effect.controls.find(c=>c.id==='pan'),0)",ctx),'-90');
assert.equal(vm.runInContext("afxEffectDisplayValue(effect.controls.find(c=>c.id==='pan'),180)",ctx),'90');

// A loaded instance uses a full panel with unknown values, not captured defaults.
ctx.panels = fixture.effects;
vm.runInContext(`AFX_TEST_DEVICE_VIEW=true;AFX_TEST_STATE={available:true,allowed_channels:[0],channels:{'0':[{type:70,instance:1},{type:78,instance:0}]}};
  AFX_TEST_CHOICES=panels.map(e=>({id:e.id,type_id:e.id==='turboensembler'?70:78,panel:e}));`,ctx);
assert.equal(vm.runInContext('afxTestDraft(0,0).effect.id',ctx),'turboensembler');
assert.equal(vm.runInContext('afxTestDraft(0,1).effect.id',ctx),'bbdchorus');
assert.equal(vm.runInContext('Object.values(afxTestDraft(0,0).values).every(v=>v===null)',ctx),true);
assert.equal(vm.runInContext('AFX_TEST_DRAFTS.size',ctx),0,'Read-only panels cannot collide with the Memory Cat instance cache');
const css = fs.readFileSync(path.join(ROOT,'webui/static/afx-modulation.css'),'utf8');
assert.match(css,/\.afx-knob \{ background:conic-gradient\(from 225deg,#76b49d 270deg/);
assert.doesNotMatch(css,/\.afx-knob-cap[^}]*transform:/);
console.log('Modulation checks passed (shared layouts, byte255, Space, opaque bytes, unknown state, loaded instances, no new writes).');
