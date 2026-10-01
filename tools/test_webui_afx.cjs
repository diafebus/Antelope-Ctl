// Hardware-free AFX popup lifecycle checks: node tools/test_webui_afx.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {ROOT} = require('./webui_sources.cjs');

const html = fs.readFileSync(path.join(ROOT, 'webui/static/index.html'), 'utf8');
assert.match(html, /data-rtab="matrix"[^]*?id="afxopen"[^]*?data-rtab="mix1"/);
// The routing tab delegate must not treat the popup button as a tab switch.
const launcherHTML = html.match(/<button[^>]*id="afxopen"[^>]*>/)[0];
assert.doesNotMatch(launcherHTML, /\btabbtn\b|data-rtab=/);

const button = {
  expanded: 'false', on: false,
  classList: {toggle(_name, on) { button.on = on; }},
  setAttribute(_name, value) { button.expanded = value; },
  addEventListener(_name, handler) { button.click = handler; },
};
const messages = new Map();
const parentEvents = {};
let openCount = 0, blocked = false, lastPopup;
const context = vm.createContext({
  PROFILE: JSON.parse(fs.readFileSync(path.join(ROOT, 'profiles/orion_studio_sc.json'), 'utf8')),
  document: {getElementById: () => button},
  window: {
    addEventListener(name, handler) { parentEvents[name] = handler; },
    open() {
      openCount++;
      if (blocked) return null;
      const events = {};
      const node = () => ({
        addEventListener(name, handler) { this[name] = handler; },
        focus() { this.focused = true; },
      });
      const nodes = Object.fromEntries(['afx-device', 'afx-channel', 'afx-channel-name',
        'afx-rack-title', 'afx-rack', 'afx-preview-status', 'afx-slot-list', 'afx-pair-control'].map(id => [id, node()]));
      const device = nodes['afx-device'], closeButton = node();
      const popup = {
        closed: false, focused: 0, events, device, closeButton, nodes,
        document: {
          body: {innerHTML: '', addEventListener() {}}, open() {}, write() {}, close() {},
          getElementById(id) { return nodes[id]; },
          querySelector() { return closeButton; },
        },
        addEventListener(name, handler) { events[name] = handler; },
        focus() { this.focused++; },
        close() { this.closed = true; events.pagehide?.(); },
      };
      lastPopup = popup;
      return popup;
    },
  },
  reportMessage: (key, title, body) => messages.set(key, {title, body}),
  clearMessage: key => messages.delete(key),
  setTimeout, clearTimeout,
  fetch() { throw new Error('The capacity popup must not make device or account requests'); },
  post() { throw new Error('The capacity popup must not issue device writes'); },
});
// Capacity-only behavior must stay request-free when no device pilot is enabled.
context.PROFILE.runtime_contracts.afx_memorycat_test.enabled = false;
vm.runInContext(fs.readFileSync(path.join(ROOT, 'webui/static/ui/afx.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'webui/static/ui/afx-memorycat.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'webui/static/ui/afx-test.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'webui/static/ui/afx-live.js'), 'utf8'), context);

// Orion dimensions come from its profile; slots are unknown, never fake empty.
button.click();
const first = lastPopup;
assert.equal((first.document.body.innerHTML.match(/<option /g) || []).length, 32);
assert.equal((first.document.body.innerHTML.match(/class="afx-channel"/g) || []).length, 1);
assert.equal((first.document.body.innerHTML.match(/class="afx-rack-unit"/g) || []).length, 8);
assert.match(first.document.body.innerHTML, /state unavailable/);
assert.equal(first.device.textContent, context.PROFILE.device.label || context.PROFILE.device.name);
assert.equal(button.expanded, 'true');
assert.equal(first.nodes['afx-channel'].focused, true);

// Channel selection repaints only that rack and is bounded by the profile.
first.nodes['afx-channel'].change({target: {value: '31'}});
assert.equal(first.nodes['afx-channel-name'].textContent, 'AFX 32');
assert.equal(first.nodes['afx-channel'].value, '31');
assert.match(first.nodes['afx-rack-title'].textContent, /AFX 32/);
assert.equal((first.nodes['afx-rack'].innerHTML.match(/class="afx-rack-unit"/g) || []).length, 8);
assert.match(first.nodes['afx-rack'].innerHTML, /AFX 32, slot 1: state unavailable/);
const lastRack = first.nodes['afx-rack'].innerHTML;
for (const value of ['32', '-1', '1.5', 'not-a-channel']) {
  first.nodes['afx-channel'].change({target: {value}});
  assert.equal(first.nodes['afx-rack'].innerHTML, lastRack);
}
button.click();
assert.equal(openCount, 1);
assert.equal(first.focused, 2);
first.events.keydown({key: 'Escape'});
assert.equal(first.closed, true);
assert.equal(button.expanded, 'false');

blocked = true;
button.click();
assert.equal(button.on, false);
assert.ok(messages.has('afx-popup'));
blocked = false;
button.click();
assert.equal(messages.has('afx-popup'), false);
lastPopup.closeButton.click();
assert.equal(button.expanded, 'false');
button.click();
assert.match(lastPopup.document.body.innerHTML, /<option value="31" selected>AFX 32<\/option>/);
lastPopup.close();

// Missing or invalid capacity does not inherit Orion's counts.
context.PROFILE = {};
const before = openCount;
button.click();
context.PROFILE = {afx: {channel_count: 32, slots_per_channel: 0}};
button.click();
assert.equal(openCount, before);

// Another declared capacity and an untrusted label remain presentation data.
context.PROFILE = {afx: {channel_count: 2, slots_per_channel: 3},
  device: {label: '<img src=x onerror=alert(1)>'}};
button.click();
assert.equal((lastPopup.document.body.innerHTML.match(/class="afx-rack-unit"/g) || []).length, 3);
assert.equal((lastPopup.document.body.innerHTML.match(/<option /g) || []).length, 2);
assert.match(lastPopup.document.body.innerHTML, /<option value="0" selected>AFX 1<\/option>/);
assert.doesNotMatch(lastPopup.document.body.innerHTML, /<img/);
assert.equal(lastPopup.device.textContent, context.PROFILE.device.label);
lastPopup.close();
assert.equal(button.expanded, 'false');
button.click();
parentEvents.pagehide();
assert.equal(lastPopup.closed, true);
assert.equal(button.on, false);
async function checkEffectPreviews() {
  context.PROFILE = JSON.parse(fs.readFileSync(path.join(ROOT, 'profiles/orion_studio_sc.json'), 'utf8'));
  context.PROFILE.runtime_contracts.afx_memorycat_test.enabled = false;
  const effect = JSON.parse(fs.readFileSync(path.join(ROOT, 'profiles/afx_effects.json'), 'utf8'))
    .effects.find(item => item.id === 'memory_brigade');
  const implementation = effect.implementations.find(item => item.profile === 'orion_studio_sc.json');
  const controls = Object.entries(implementation.control_encodings).map(([id, field]) => ({
    id, label: field.label, kind: field.kind, range: field.display_range, options: field.options,
  }));
  let requests = 0;
  context.fetch = async (url, options) => {
    assert.equal(url, '/api/afx/catalog');
    assert.equal(options, undefined, 'Preview must use a metadata GET only');
    requests++;
    return {ok: true, json: async () => ({mode: 'preview', device_writes: false,
      effects: [{id: effect.id, name: effect.name, controls}]})};
  };
  button.click();
  vm.runInContext('selectAfxChannel(0)', context);
  await vm.runInContext("previewAfxEffect(0, 'memory_brigade')", context);
  const popup = lastPopup;
  assert.equal(requests, 1);
  assert.equal((popup.nodes['afx-rack'].innerHTML.match(/type="range"/g) || []).length, 6);
  assert.equal((popup.nodes['afx-rack'].innerHTML.match(/class="afx-mode-button"/g) || []).length, 4);
  assert.match(popup.nodes['afx-rack'].innerHTML, /Local preview/);
  assert.match(popup.nodes['afx-preview-status'].textContent, /do not load an effect/);

  const properties = {}, output = {};
  const group = {style: {setProperty(name, value) { properties[name] = value; }},
    querySelector() { return output; }};
  const input = {dataset: {afxSlot: '0', afxControl: 'level'}, value: '100',
    closest() { return group; }, matches() { return true; }};
  popup.nodes['afx-rack'].input({target: input});
  assert.equal(output.textContent, '100');
  assert.equal(properties['--afx-turn'], '135deg');
  input.value = '101';
  popup.nodes['afx-rack'].input({target: input});
  assert.equal(output.textContent, '100', 'Out-of-range input cannot change a draft');
  input.value = '0';
  popup.nodes['afx-rack'].input({target: input});
  assert.equal(properties['--afx-turn'], '-135deg');
  input.value = '42';
  popup.nodes['afx-rack'].input({target: input});

  // Dragging a knob changes only the draft; another pointer cannot move it.
  const handlers = {};
  const knobGroup = {querySelector: selector => selector === 'input' ? input : output,
    style: group.style};
  input.closest = () => knobGroup;
  const knob = {dataset: {afxSlot: '0'},
    closest: () => knobGroup,
    setPointerCapture(id) { this.pointer = id; },
    hasPointerCapture(id) { return this.pointer === id; },
    releasePointerCapture() { this.pointer = null; },
    addEventListener(name, handler) { handlers[name] = handler; },
    removeEventListener(name) { delete handlers[name]; }};
  const knobTarget = {closest: selector => selector === '[data-afx-slot]' || selector === '[data-afx-knob]' ? knob : null};
  popup.nodes['afx-rack'].pointerdown({target: knobTarget, button: 0, pointerId: 7,
    clientY: 100, preventDefault() {}});
  handlers.pointermove({pointerId: 8, clientY: 0});
  assert.equal(input.value, '42');
  handlers.pointermove({pointerId: 7, clientY: 80});
  assert.equal(input.value, '52');
  handlers.pointermove({pointerId: 7, clientY: 80, shiftKey: true});
  assert.equal(input.value, '44');
  handlers.pointerup({pointerId: 7});
  assert.equal(knob.pointer, null);
  assert.equal(Object.keys(handlers).length, 0);
  input.value = '42';
  popup.nodes['afx-rack'].input({target: input});

  const modeButton = (value) => ({dataset: {afxSlot: '0', afxMode: 'chrs_vibr', afxValue: value},
    setAttribute(_key, value) { this.pressed = value; }});
  const chorus = modeButton('chorus'), vibrato = modeButton('vibrato');
  for (const option of [chorus, vibrato]) option.parentElement = {querySelectorAll: () => [chorus, vibrato]};
  vibrato.closest = selector => ['[data-afx-slot]', '[data-afx-mode]'].includes(selector) ? vibrato : null;
  popup.nodes['afx-rack'].click({target: vibrato});
  assert.equal(vibrato.pressed, 'true');
  assert.equal(chorus.pressed, 'false');

  // Moving the bottom effect to the top preserves both drafts, including modes.
  await vm.runInContext("previewAfxEffect(7, 'memory_brigade')", context);
  vm.runInContext("AFX_DRAFTS.get('0:7').values.level = 88", context);
  const transfer = {value: '', setData(_type, value) { this.value = value; }, getData() { return this.value; }};
  const handle = {dataset: {afxDrag: '7'}, closest: selector => selector === '[data-afx-drag]' ? handle : null};
  const destination = {dataset: {afxRackSlot: '0'}, closest: selector => selector === '[data-afx-rack-slot]' ? destination : null};
  popup.nodes['afx-rack'].dragstart({target: handle, dataTransfer: transfer, preventDefault() {}});
  assert.equal(transfer.value, '0:7');
  popup.nodes['afx-rack'].drop({target: destination, dataTransfer: transfer, preventDefault() {}});
  assert.equal(vm.runInContext("AFX_DRAFTS.get('0:0').values.level", context), 88);
  assert.equal(vm.runInContext("AFX_DRAFTS.get('0:1').values.level", context), 42);
  assert.equal(vm.runInContext("AFX_DRAFTS.get('0:1').values.chrs_vibr", context), 'vibrato');
  transfer.value = '1:1';
  popup.nodes['afx-rack'].drop({target: destination, dataTransfer: transfer, preventDefault() {}});
  assert.equal(vm.runInContext("AFX_DRAFTS.get('0:0').values.level", context), 88, 'Cross-channel drop cannot move a draft');
  vm.runInContext('moveAfxDraft(1, 0)', context);

  vm.runInContext('selectAfxChannel(1)', context);
  assert.doesNotMatch(popup.nodes['afx-rack'].innerHTML, /type="range"/);
  await vm.runInContext("previewAfxEffect(0, 'memory_brigade')", context);
  assert.equal(requests, 1, 'A local catalog is cached, rather than fetched per control');
  vm.runInContext('selectAfxChannel(0)', context);
  assert.match(popup.nodes['afx-rack'].innerHTML, /value="42"[^]*?data-afx-control="level"/);
  assert.match(popup.nodes['afx-rack'].innerHTML, /aria-pressed="true"[^]*?data-afx-value="vibrato"/);
  popup.close();
  button.click();
  assert.match(lastPopup.document.body.innerHTML, /value="42"[^]*?data-afx-control="level"/);
  const remove = {dataset: {afxRemove: '0'}, closest: selector => selector === '[data-afx-remove]' ? remove : null};
  lastPopup.nodes['afx-rack'].click({target: remove});
  assert.equal((lastPopup.nodes['afx-rack'].innerHTML.match(/type="range"/g) || []).length, 6);
  vm.runInContext("AFX_DRAFTS.delete('0:1')", context);

  // Closing the window during a slow metadata GET must not repaint a new popup.
  let release;
  context.fetch = () => new Promise(resolve => { release = resolve; });
  vm.runInContext('AFX_PREVIEW_CATALOG = null', context);
  const pending = vm.runInContext("previewAfxEffect(2, 'memory_brigade')", context);
  lastPopup.close();
  button.click();
  const reopened = lastPopup;
  release({ok: true, json: async () => ({mode: 'preview', device_writes: false,
    effects: [{id: effect.id, name: effect.name, controls}]})});
  await pending;
  assert.doesNotMatch(reopened.document.body.innerHTML, /type="range"/);
  reopened.close();

  // Opening reads metadata only; the first edit sends a complete starting block.
  const emptySlots = Array.from({length: 8}, () => ({type: 0, instance: 0}));
  emptySlots[0] = {type: 73, instance: 4};
  const state = {available: true, online: true, writes_enabled: true, slots: emptySlots,
    channels: Object.fromEntries(Array.from({length:32}, (_,i) => [String(i), i === 0 ? emptySlots : Array.from({length:8}, () => ({type:0,instance:0}))])),
    allowed_channels: Array.from({length:32},(_,i)=>i), parameters: {}, session: 1, links: Array(16).fill(null), effects: [
      {id: 'memory_brigade', name: 'Memory Cat Brigade', category: 'Delay & Reverb', type_id: 73, loadable: true},
      {id: 'instinct', name: 'Instinct', category: 'Dynamics', type_id: 75, loadable: true},
      {id: 'deesser', name: 'Master De-Esser', category: 'Dynamics', type_id: 27, loadable: true},
      {id: 'unmapped', name: 'Unmapped effect', type_id: null, loadable: false},
    ]};
  const writes = [];
  let deviceReads = 0;
  context.fetch = async (url, options) => {
    assert.match(url, /^\/api\/afx\/(memorycat-test|link)/);
    if (options) {
      assert.equal(options.method, 'POST');
      writes.push({url, body: JSON.parse(options.body)});
      if (url.endsWith('/link')) state.links[writes.at(-1).body.pair] = writes.at(-1).body.enabled;
    } else deviceReads++;
    return {ok: true, json: async () => options && url.endsWith('/parameters') ? {sent: true, verified: false} : state};
  };
  context.PROFILE.runtime_contracts.afx_memorycat_test.enabled = true;
  vm.runInContext('AFX_CHANNEL = 0', context);
  button.click();
  await new Promise(resolve => setImmediate(resolve));
  const live = lastPopup;
  assert.equal(deviceReads, 1, 'Opening the enabled pilot automatically reads the device rack');
  assert.equal(writes.length, 0, 'Opening the rack must never write to the device');
  assert.equal(live.nodes['afx-channel'].value, '0', 'Opening retains the selected device channel');
  assert.match(live.nodes['afx-rack'].innerHTML, /Device test/);
  assert.equal((live.nodes['afx-slot-list'].innerHTML.match(/data-afx-effect-select=/g) || []).length, 8);
  assert.match(live.nodes['afx-slot-list'].innerHTML, /value="unmapped" disabled/);
  assert.match(live.nodes['afx-slot-list'].innerHTML, /<optgroup label="Dynamics">/);
  assert.match(live.nodes['afx-slot-list'].innerHTML, /<optgroup label="Delay &amp; Reverb">/);
  assert.doesNotMatch(live.nodes['afx-channel'].innerHTML, /link \?/);
  assert.match(live.document.body.innerHTML, /afx-channel-heading[^]*?afx-channel-name[^]*?afx-pair-control/);
  assert.doesNotMatch(live.nodes['afx-rack'].innerHTML, /data-afx-effect-select=/);
  assert.doesNotMatch(live.nodes['afx-rack'].innerHTML, /Preview Memory/);
  assert.match(live.nodes['afx-slot-list'].innerHTML, /Memory Cat/);
  assert.equal((live.nodes['afx-slot-list'].innerHTML.match(/value="" selected/g) || []).length, 7);
  vm.runInContext('selectAfxChannel(1)', context);
  assert.match(live.nodes['afx-slot-list'].innerHTML, /data-afx-effect-select="0"[^>]*>/);
  assert.doesNotMatch(live.nodes['afx-slot-list'].innerHTML, /data-afx-effect-select="0"[^>]* disabled/);
  vm.runInContext('selectAfxChannel(0)', context);
  assert.doesNotMatch(live.nodes['afx-rack'].innerHTML, /Apply all settings|data-afx-device-apply/);
  assert.match(live.nodes['afx-rack'].innerHTML, /First edit sends all displayed starting values/);
  assert.equal(vm.runInContext('afxTestDraft(0, 0).values.level', context), 100);
  live.nodes['afx-rack'].input({target: input});
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(writes.length, 1);
  assert.equal(writes[0].body.channel, 0);
  assert.equal(writes[0].body.instance, 4);
  assert.equal(writes[0].body.values.level, 42);
  assert.equal(writes[0].body.values.chrs_vibr, 0);
  assert.equal(writes[0].body.values.size, 0);
  assert.equal(Object.keys(writes[0].body.values).length, 8);
  assert.equal(vm.runInContext('afxTestDraft(0, 0).liveReady', context), true);
  assert.match(live.nodes['afx-preview-status'].textContent, /Live settings sent/);

  // Rapid knob turns coalesce to the latest full state, without replacing DOM.
  const beforeLive = live.nodes['afx-rack'].innerHTML;
  const liveSwitch = modeButton('1');
  liveSwitch.closest = selector => ['[data-afx-slot]', '[data-afx-mode]'].includes(selector) ? liveSwitch : null;
  liveSwitch.parentElement = {querySelectorAll: () => [liveSwitch]};
  live.nodes['afx-rack'].click({target: liveSwitch});
  for (const value of ['43', '44', '45']) {
    input.value = value;
    live.nodes['afx-rack'].input({target: input});
  }
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(writes.length, 2);
  assert.equal(writes[1].body.values.level, 45);
  assert.equal(writes[1].body.values.chrs_vibr, 1, 'Switch edits share the live queue');
  assert.equal(live.nodes['afx-rack'].innerHTML, beforeLive, 'Live sends preserve pointer-captured controls');
  assert.match(live.nodes['afx-preview-status'].textContent, /Live settings sent/);
  // Instance drafts follow chain reorder and are discarded on reconnection.
  state.channels[0] = state.slots = [{type: 0, instance: 0}, ...emptySlots.slice(0, 7)];
  await vm.runInContext("afxTestRequest('/api/afx/memorycat-test')", context);
  assert.equal(vm.runInContext('afxTestDraft(0, 1).values.level', context), 45);
  state.session = 2;
  state.parameters = {};
  await vm.runInContext("afxTestRequest('/api/afx/memorycat-test')", context);
  assert.equal(vm.runInContext('afxTestDraft(0, 1).values.chrs_vibr', context), '0');
  assert.equal(vm.runInContext('afxTestDraft(0, 1).liveReady', context), false);
  assert.equal(writes.length, 2);
  const previewButton = {closest: selector => selector === '[data-afx-test-preview]' ? previewButton : null};
  vm.runInContext('afxTestClick', context)({target: previewButton});
  assert.match(live.nodes['afx-rack'].innerHTML, /Preview Memory/);
  assert.match(live.nodes['afx-preview-status'].textContent, /do not load effects/);
  const refreshButton = {closest: selector => selector === '[data-afx-test-refresh]' ? refreshButton : null};
  vm.runInContext('afxTestClick', context)({target: refreshButton});
  await new Promise(resolve => setImmediate(resolve));
  assert.match(live.nodes['afx-slot-list'].innerHTML, /data-afx-effect-select/);
  assert.equal(writes.length, 2, 'Switching rack views only reads metadata');
  const picker = {dataset: {afxEffectSelect: '0'}, value: 'unmapped', matches: () => true};
  live.nodes['afx-slot-list'].change({target: picker});
  assert.equal(writes.length, 2, 'Unmapped effect choices must not produce writes');
  picker.value = 'instinct';
  live.nodes['afx-slot-list'].change({target: picker});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(writes[2].body.operation, 'load');
  assert.equal(writes[2].body.effect_id, 'instinct');
  assert.equal(writes[2].body.slot, 0);
  for (const channel of [0, 1, 2, 3, 30, 31]) {
    vm.runInContext(`selectAfxChannel(${channel})`, context);
    const pair = Math.floor(channel / 2);
    assert.match(live.nodes['afx-pair-control'].innerHTML, new RegExp(`aria-label="Link AFX ${pair * 2 + 1}–${pair * 2 + 2}"`));
  }
  vm.runInContext('selectAfxChannel(2)', context);
  const pairButton = {dataset: {afxPair: '1'}, closest: selector => selector === '[data-afx-pair]' ? pairButton : null};
  live.nodes['afx-pair-control'].click({target: pairButton});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(writes.at(-1).body.pair, 1);
  assert.equal(writes.at(-1).body.enabled, true);
  assert.match(live.nodes['afx-channel'].innerHTML, /AFX 3 ↔ 4/);
  assert.match(live.nodes['afx-channel'].innerHTML, /AFX 4 ↔ 3/);
  assert.match(live.nodes['afx-pair-control'].innerHTML, /Unlink AFX 3–4/);
  live.nodes['afx-pair-control'].click({target: pairButton});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(writes.at(-1).body.enabled, false);
  assert.doesNotMatch(live.nodes['afx-channel'].innerHTML, /AFX 3 ↔ 4/);
  // The left selector sends the selected channel; both drag surfaces share it.
  vm.runInContext('selectAfxChannel(31)', context);
  picker.value = 'deesser';
  live.nodes['afx-slot-list'].change({target: picker});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(writes.at(-1).body.channel, 31);
  assert.equal(writes.at(-1).body.effect_id, 'deesser');
  state.channels[31][7] = {type:73,instance:6};
  await vm.runInContext("afxTestRequest('/api/afx/memorycat-test')", context);
  const leftHandle = {dataset: {afxDrag:'7'}, closest: selector => selector === '[data-afx-drag]' ? leftHandle : null};
  const leftTarget = {dataset: {afxListSlot:'1'}, closest: selector => selector === '[data-afx-list-slot]' ? leftTarget : null};
  const drag = {value:'',setData(_type,value){this.value=value;},getData(){return this.value;}};
  live.nodes['afx-slot-list'].dragstart({target:leftHandle,dataTransfer:drag,preventDefault(){}});
  assert.equal(drag.value, '31:7');
  live.nodes['afx-rack'].drop({target:destination,dataTransfer:drag,preventDefault(){}});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(writes.at(-1).body.channel, 31);
  assert.equal(writes.at(-1).body.source, 7);
  assert.equal(writes.at(-1).body.slot, 0);
  live.nodes['afx-rack'].dragstart({target:leftHandle,dataTransfer:drag,preventDefault(){}});
  live.nodes['afx-slot-list'].drop({target:leftTarget,dataTransfer:drag,preventDefault(){}});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(writes.at(-1).body.slot, 1);
  // Readback guards this pair only; another linked pair does not block it.
  state.link_readback = true;
  state.links.fill(false);
  state.links[0] = true;
  await vm.runInContext("afxTestRequest('/api/afx/memorycat-test')", context);
  assert.doesNotMatch(live.nodes['afx-slot-list'].innerHTML, /data-afx-effect-select="0"[^>]* disabled/);
  state.links[15] = true;
  await vm.runInContext("afxTestRequest('/api/afx/memorycat-test')", context);
  assert.match(live.nodes['afx-slot-list'].innerHTML, /data-afx-effect-select="0"[^>]* disabled/);
  assert.match(live.nodes['afx-pair-control'].innerHTML, /Device link readback/);
  state.links.fill(false);
  // First edit after reconnect sends immediately; stale channel/draft/link edits do not.
  vm.runInContext('selectAfxChannel(0)', context);
  input.dataset.afxSlot = '1';
  input.value = '39';
  live.nodes['afx-rack'].input({target: input});
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(writes.at(-1).body.instance, 4);
  assert.equal(writes.at(-1).body.values.level, 39);
  assert.equal(writes.at(-1).body.values.chrs_vibr, 0);
  assert.equal(vm.runInContext('afxTestDraft(0, 1).liveReady', context), true);
  const beforeStale = writes.length;
  live.nodes['afx-rack'].input({target: input});
  vm.runInContext('selectAfxChannel(1)', context);
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(writes.length, beforeStale, 'Queued edits cannot follow a channel change');
  vm.runInContext('selectAfxChannel(0)', context);
  live.nodes['afx-rack'].input({target: input});
  vm.runInContext('AFX_TEST_DRAFTS.delete(4); afxTestDraft(0, 1)', context);
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(writes.length, beforeStale, 'Reused instance IDs cannot receive an old draft');
  live.nodes['afx-rack'].input({target: input});
  state.links[0] = true;
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(writes.length, beforeStale, 'Link state is checked again before sending');
  state.links[0] = false;
  // A failed live send pauses this instance and is never retried.
  vm.runInContext('selectAfxChannel(0)', context);
  let failedRequests = 0;
  context.fetch = async () => { failedRequests++; return {ok: false, json: async () => ({error: 'test failure'})}; };
  vm.runInContext('afxLiveChanged(afxTestDraft(0, 1))', context);
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(failedRequests, 1);
  assert.equal(vm.runInContext('afxTestDraft(0, 1).livePaused', context), true);
  vm.runInContext('afxLiveChanged(afxTestDraft(0, 1))', context);
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(failedRequests, 1);
  const resume = {dataset: {afxDeviceResume: '1'}, closest: selector => selector === '[data-afx-device-resume]' ? resume : null};
  context.fetch = async () => { failedRequests++; return {ok: true, json: async () => ({sent: true, verified: false})}; };
  live.nodes['afx-rack'].click({target: resume});
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(failedRequests, 2, 'Only an explicit retry resumes failed sending');
  assert.equal(vm.runInContext('afxTestDraft(0, 1).livePaused', context), false);
  // A slow acknowledgement keeps one request in flight and sends the latest turn next.
  const slowWrites = [];
  let releaseFirst;
  context.fetch = async (_url, options) => {
    slowWrites.push(JSON.parse(options.body));
    if (slowWrites.length === 1) await new Promise(resolve => { releaseFirst = resolve; });
    return {ok: true, json: async () => ({sent: true, verified: false})};
  };
  input.value = '40';
  live.nodes['afx-rack'].input({target: input});
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(slowWrites.length, 1);
  for (const value of ['41', '42']) {
    input.value = value;
    live.nodes['afx-rack'].input({target: input});
  }
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(slowWrites.length, 1, 'No overlapping parameter requests');
  releaseFirst();
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(slowWrites.length, 2);
  assert.equal(slowWrites[1].values.level, 42);
  live.close();
  console.log('AFX checks passed (effect picker, pair links, live coalescing, failure pause, reconnect).');
}

checkEffectPreviews().catch(error => { console.error(error); process.exitCode = 1; });
