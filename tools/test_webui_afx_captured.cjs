// Interactive capture-backed local panels; no device or browser dependency.
const assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'),vm=require('node:vm');
const {ROOT}=require('./webui_sources.cjs');
const fixture=JSON.parse(fs.readFileSync(path.join(ROOT,'tools/fixtures/afx_captured_presentations.json')));
const ctx=vm.createContext({PROFILE:JSON.parse(fs.readFileSync(path.join(ROOT,'profiles/orion_studio_sc.json'))),
 document:{getElementById:()=>({addEventListener(){}})},window:{addEventListener(){}},setTimeout,clearTimeout,
 fetch(){throw Error('Panel gestures cannot send requests');}});
for(const file of ['afx','afx-controls','afx-captured','afx-powergate','afx-powerex','afx-veq1a','afx-vmeq5','afx-deesser','afx-test','afx-live'])
 vm.runInContext(fs.readFileSync(path.join(ROOT,`webui/static/ui/${file}.js`),'utf8'),ctx);
ctx.fixture=fixture;
for(const effect of fixture.effects){
 ctx.effect=effect;
 const html=vm.runInContext(`AFX_PANELS.get(effect.id).render({effect,live:true,removable:false,parameterAvailable:false,values:Object.fromEntries(effect.controls.map(c=>[c.id,null]))},0)`,ctx);
 assert.match(html,/Device values unavailable/);
 assert.ok([...html.matchAll(/<(?:input|select)[^>]*data-afx-control[^>]*>/g)].every(m=>/disabled/.test(m[0])));
 assert.ok([...html.matchAll(/<button[^>]*data-afx-mode[^>]*>/g)].every(m=>/disabled/.test(m[0])));
 assert.match(html,/<button[^>]*data-afx-device-remove[^>]* disabled/);
 vm.runInContext(`draft={effect,live:true,parameterAvailable:false,values:{}};afxEffectInput(draft,{dataset:{afxControl:effect.controls[0].id},value:'1'});`,ctx);
 assert.equal(vm.runInContext('Object.keys(draft.values).length',ctx),0);
}
// An unidentified selector must not masquerade as four usable named modes.
const deesserHTML=vm.runInContext(`effect=fixture.effects.find(e=>e.id==='deesser');AFX_PANELS.get('deesser').render({effect,live:false,values:Object.fromEntries(effect.controls.map(c=>[c.id,c.default]))},0)`,ctx);
assert.match(deesserHTML,/Mode meanings unverified/);
assert.match(deesserHTML,/<select[^>]*data-afx-control="ctrl"[^>]* disabled/);
assert.doesNotMatch(deesserHTML,/Position [1-4]|data-afx-mode="ctrl"/);
assert.equal([...deesserHTML.matchAll(/data-afx-mode="processing"/g)].length,2,'Only one processing control pair');
const properties={},output={},doc={querySelectorAll:()=>[],querySelector:()=>null};
const group={style:{setProperty:(k,v)=>properties[k]=v},querySelector:()=>output};
ctx.input={dataset:{afxControl:'attack',afxSlot:'0'},value:'0.2',closest:()=>group,ownerDocument:doc};
vm.runInContext(`effect=fixture.effects.find(e=>e.id==='powergate');draft={effect,live:false,slot:0,values:{attack:.1}};afxEffectInput(draft,input)`,ctx);
assert.equal(vm.runInContext('draft.values.attack',ctx),.2);
ctx.input.value='.25';vm.runInContext('afxEffectInput(draft,input)',ctx);
assert.equal(vm.runInContext('draft.values.attack',ctx),.2,'Off-step fractions rejected');
ctx.input.dataset.afxControl='mid_freq';ctx.input.value='10';
vm.runInContext(`effect=fixture.effects.find(e=>e.id==='pultec_meq');draft={effect,live:false,slot:0,values:{mid_freq:'0'}};afxEffectInput(draft,input)`,ctx);
assert.equal(vm.runInContext('draft.values.mid_freq',ctx),'10');assert.equal(properties['--afx-turn'],'135deg');
ctx.input.value='11';vm.runInContext('afxEffectInput(draft,input)',ctx);
assert.equal(vm.runInContext('draft.values.mid_freq',ctx),'10');
const q={dataset:{afxSlot:'0'},closest:()=>({classList:{toggle(){}}})};
const button={dataset:{afxMode:'filter_type',afxValue:'3'},disabled:false,setAttribute(){},parentElement:{querySelectorAll:()=>[button]},ownerDocument:{querySelectorAll:()=>[q],querySelector:()=>null}};
ctx.event={target:{closest:()=>button}};
vm.runInContext(`effect=fixture.effects.find(e=>e.id==='deesser');draft={effect,live:false,slot:0,values:{filter_type:'0',q_factor:1}};afxEffectClick(draft,event)`,ctx);
assert.equal(q.disabled,false,'BandPass enables Q');
button.dataset.afxValue='0';vm.runInContext('afxEffectClick(draft,event)',ctx);
assert.equal(q.disabled,true,'HighPass disables Q');
assert.equal(vm.runInContext('draft.values.q_factor',ctx),1,'Local dependency preserves Q draft');
(async()=>{
 const status={};ctx.popup={closed:false,document:{getElementById:()=>status}};
 vm.runInContext('AFX_WINDOW=popup;AFX_CHANNEL=0;selectAfxChannel=()=>{};AFX_TEST_DEVICE_VIEW=false;AFX_DRAFTS.clear();',ctx);
 let release;ctx.fetch=()=>new Promise(resolve=>{release=()=>resolve({ok:true,json:async()=>fixture});});
 const pending=vm.runInContext("previewAfxEffect(0,'powergate')",ctx);
 vm.runInContext('AFX_TEST_DEVICE_VIEW=true',ctx);release();await pending;
 assert.equal(vm.runInContext('AFX_DRAFTS.size',ctx),0,'Mode change cancels pending local loading');
 vm.runInContext('AFX_TEST_DEVICE_VIEW=false;AFX_PREVIEW_CATALOG=null',ctx);
 const cancelled=vm.runInContext("previewAfxEffect(0,'powergate')",ctx);
 ctx.selectEvent={target:{matches:()=>true,dataset:{afxLocalSelect:'0'},value:''}};
 vm.runInContext('changeAfxPreview(selectEvent)',ctx);release();await cancelled;
 assert.equal(vm.runInContext('AFX_DRAFTS.size',ctx),0,'Empty selection cancels pending local loading');
 console.log('Captured panel checks passed (five panels, unknown live state, decimal steps, detents, Q dependency, async isolation).');
})().catch(e=>{console.error(e);process.exitCode=1;});
