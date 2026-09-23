// Offline device-backed input-link checks: node tools/test_webui_input_links.cjs
const assert = require('node:assert/strict');
const vm = require('node:vm');

const {readWebUISource} = require('./webui_sources.cjs');
const js = readWebUISource();
const source = js.slice(js.indexOf('function inputLinkReadbackSpec'),
  js.indexOf('function digCurGain'));
const saves = {preamp: 0, adat: 0, paintPreamp: 0, paintAdat: 0};
const context = vm.createContext({
  PROFILE: {frame: {link_command: {readback: {
    status: 'capture-confirmed', category: 0x0b, index: 0,
    record_count: 6, pair_counts: {preamp: 6, adat: 6},
  }}}},
  N_PAIRS: 6,
  LINKS: {0: true},
  DIG: {adat: {pairs: 8, links: {0: true, 7: true}}},
  saveLinks: () => saves.preamp++,
  digSaveLinks: kind => { assert.equal(kind, 'adat'); saves.adat++; },
  refreshLinks: () => saves.paintPreamp++,
  digRefreshLinks: kind => { assert.equal(kind, 'adat'); saves.paintAdat++; },
});
vm.runInContext(source, context);

const records = Array.from({length: 6}, (_, record_index) => ({
  record_index, linked: record_index === 3 ? 1 : 0,
}));
const payload = (rows, index = 0) => ({layouts: [{
  kind: 'link_table', category: 0x0b, index, record_count: 6,
  safe: true, current: {[index]: rows},
}]});

// Incomplete, duplicated, or malformed tables cannot clear a saved link.
assert.equal(context.syncInputLinksFromReadback(payload(records.slice(0, 5))), false);
assert.equal(context.syncInputLinksFromReadback(payload([
  ...records.slice(0, 5), {...records[4]},
])), false);
assert.equal(context.syncInputLinksFromReadback(payload([
  ...records.slice(0, 5), {record_index: 5},
])), false);
assert.equal(context.LINKS[0], true);
assert.equal(context.DIG.adat.links[0], true);

// Index 0 is the captured space-0 pair flag for preamps and ADAT pairs 0..5.
assert.equal(context.syncInputLinksFromReadback(payload(records)), true);
assert.equal(context.LINKS[0], undefined);
assert.equal(context.LINKS[3], true);
assert.equal(context.DIG.adat.links[0], undefined);
assert.equal(context.DIG.adat.links[3], true);
assert.equal(context.DIG.adat.links[7], true); // no confirmed device map for pairs 6/7
assert.deepEqual(saves, {preamp: 1, adat: 1, paintPreamp: 1, paintAdat: 1});

// The separate ADAT schema table stayed zero during the live transition.
assert.equal(context.syncInputLinksFromReadback(payload(records.map(row => ({
  ...row, linked: 0,
})), 1)), false);
assert.equal(context.DIG.adat.links[3], true);

assert.equal(context.syncInputLinksFromReadback(payload(records.map(row => ({
  ...row, linked: 0,
})))), true);
assert.equal(context.LINKS[3], undefined);
assert.equal(context.DIG.adat.links[3], undefined);
assert.equal(context.DIG.adat.links[7], true);

context.PROFILE.frame.link_command.readback.status = 'provisional';
context.LINKS[0] = true;
assert.equal(context.syncInputLinksFromReadback(payload(records)), false);
assert.equal(context.LINKS[0], true);
console.log('WebUI input link readback checks passed.');
