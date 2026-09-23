// Offline device-backed input-link checks: node tools/test_webui_input_links.cjs
const assert = require('node:assert/strict');
const vm = require('node:vm');

const {readWebUISource} = require('./webui_sources.cjs');
const js = readWebUISource();
const source = js.slice(js.indexOf('function inputLinkReadbackSpec'),
  js.indexOf('function digCurGain'));
const saves = {preamp: 0, adat: 0, paintPreamp: 0, paintAdat: 0};
const partnerPosts = [];
const context = vm.createContext({
  PROFILE: {frame: {link_command: {readback: {
    status: 'capture-confirmed', category: 0x0b, index: 0,
    record_count: 6, pair_counts: {preamp: 6, adat: 6},
    additional_tables: [{
      status: 'schema-backed', category: 0x0b, index: 1, record_count: 8,
      transition_confirmed: false,
      pair_mappings: {adat: {pair_start: 6, record_start: 6, pair_count: 2}},
    }],
  }}}},
  N_PAIRS: 6,
  LINKS: {0: true},
  DIG: {adat: {api: 'adat', pairs: 8, links: {0: true, 7: true}}},
  DIG_PENDING: {},
  digKey: (kind, ch) => kind + ':' + ch,
  digPartner: ch => ch % 2 ? ch - 1 : ch + 1,
  digIsLinked: (kind, ch) => !!context.DIG[kind].links[Math.floor(ch / 2)],
  post: (path, body) => partnerPosts.push({path, body}),
  saveLinks: () => saves.preamp++,
  digSaveLinks: kind => { assert.equal(kind, 'adat'); saves.adat++; },
  refreshLinks: () => saves.paintPreamp++,
  digRefreshLinks: kind => { assert.equal(kind, 'adat'); saves.paintAdat++; },
});
vm.runInContext(source, context);
assert.equal(context.inputLinkPairReadbackConfirmed('preamp', 3), true);
assert.equal(context.inputLinkPairReadbackConfirmed('adat', 5), true);
assert.equal(context.inputLinkPairReadbackConfirmed('adat', 6), false);
assert.match(context.inputLinkButtonTitle('adat', 6, 'ADAT 13+ADAT 14'),
  /device state readback not confirmed/);

const records = Array.from({length: 6}, (_, record_index) => ({
  record_index, linked: record_index === 3 ? 1 : 0,
}));
const rowsFor = (count, active = []) => Array.from({length: count}, (_, record_index) => ({
  record_index, linked: active.includes(record_index) ? 1 : 0,
}));
const layout = (rows, index = 0, count = rows.length) => ({
  kind: 'link_table', category: 0x0b, index, record_count: count,
  safe: true, current: {[index]: rows},
});
const payload = (rows, index = 0, count = rows.length) => ({
  layouts: [layout(rows, index, count)],
});

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
assert.equal(context.DIG.adat.links[7], true); // tail table has not arrived yet
assert.deepEqual(saves, {preamp: 1, adat: 1, paintPreamp: 1, paintAdat: 1});

// A schema-only table is diagnostic; it cannot overwrite an unconfirmed link state.
const tailOn = rowsFor(8, [6]);
assert.equal(context.syncInputLinksFromReadback(payload(tailOn, 1)), false);
assert.equal(context.DIG.adat.links[6], undefined);
assert.equal(context.DIG.adat.links[7], true);

// Only a transition-confirmed mapping may drive the ADAT tail indicators.
context.PROFILE.frame.link_command.readback.additional_tables[0].transition_confirmed = true;
assert.equal(context.syncInputLinksFromReadback(payload(tailOn, 1)), true);
assert.equal(context.DIG.adat.links[6], true);
assert.equal(context.DIG.adat.links[7], undefined);
assert.deepEqual(saves, {preamp: 1, adat: 2, paintPreamp: 1, paintAdat: 2});

// An incomplete or malformed tail table cannot clear an already observed pair.
assert.equal(context.syncInputLinksFromReadback(payload(tailOn.slice(0, 7), 1, 8)), false);
assert.equal(context.DIG.adat.links[6], true);

assert.equal(context.syncInputLinksFromReadback(payload(records.map(row => ({
  ...row, linked: 0,
})))), true);
assert.equal(context.LINKS[3], undefined);
assert.equal(context.DIG.adat.links[3], undefined);
assert.equal(context.syncInputLinksFromReadback(payload(rowsFor(8), 1)), true);
assert.equal(context.DIG.adat.links[6], undefined);
assert.equal(context.DIG.adat.links[7], undefined);

// When a mapped/local link is on, the real knob-send path posts the edited
// channel and the linked partner as separate device gain writes.
vm.runInContext(js.slice(js.indexOf('function digLinkSend'),
  js.indexOf('function buildDig')), context);
context.DIG.adat.links[6] = true;
context.digLinkSend('adat', 12, 1);
assert.equal(JSON.stringify(partnerPosts), JSON.stringify([
  {path: '/api/adat-gain', body: {channel: 13, db: 1}},
]));
assert.equal(context.DIG_PENDING['adat:13'].val, 1);
assert.match(js, /post\('\/api\/' \+ d\.api \+ '-gain', \{channel: ch, db: v\}\);\s*digLinkSend\(kind, ch, v\);/);

context.PROFILE.frame.link_command.readback.status = 'provisional';
context.LINKS[0] = true;
assert.equal(context.syncInputLinksFromReadback(payload(records)), false);
assert.equal(context.LINKS[0], true);
console.log('WebUI input link readback checks passed.');
