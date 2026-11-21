'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('./core.js');
const fresh = () => ({schema_version:C.SCHEMA, generated_at_utc:'2026-11-15T10:00:00Z',synthetic:false,markets:[],sources:[]});
const market = () => ({sport:'CBB',event_id:'e1',event_label:'Away @ Home',family:'First half / moneyline',state:'NO_PROVENANCE',reason:'Original authenticated book receipt missing'});

test('demo is visibly synthetic, covers seven sport families, has zero approved stakes',()=>{
  const d=C.demonstration();
  assert.equal(d.synthetic,true);
  assert.equal(d.approved_stake_u,0);
  assert.equal(d.official_count,0);
  assert.equal(d.independent_verification,false);
  assert.deepEqual(Object.keys(C.summary(d).sports),C.SPORTS);
  assert.equal(C.summary(d).eventCount,7);
  assert.ok(d.markets.every(r=>r.event_id.startsWith('DEMO-')&&r.reason.includes('SYNTHETIC')));
  assert.ok(d.markets.length>50);
});
test('imported non-demo data still cannot assert verified source, official bet or units',()=>{
  const d=C.validateSnapshot({...fresh(),markets:[market()]});
  assert.equal(d.synthetic,false);assert.equal(d.independent_verification,false);
  assert.equal(d.official_count,0);assert.equal(d.approved_stake_u,0);
});
test('empty import has zero rows and no invented events or source connections',()=>{
  const d=C.validateSnapshot(fresh()); const s=C.summary(d);
  assert.equal(s.rows,0);assert.equal(s.eventCount,0);assert.equal(s.sourceCount,0);
});
test('market counts preserve repeated original rows but event count deduplicates by sport+event ID',()=>{
  const d=C.validateSnapshot({...fresh(),markets:[market(),market(),{...market(),sport:'NFL'}]});
  const s=C.summary(d); assert.equal(s.rows,3);assert.equal(s.eventCount,2);
  assert.equal(s.states.NO_PROVENANCE,3);assert.equal(s.sports.CBB,2);
});
test('all seven sports and explicit exclusions survive without collapsing alternate families',()=>{
  const rows=C.SPORTS.flatMap((sport,i)=>[{...market(),sport,event_id:'event_'+i,family:'Alt spread 3.5',state:'NOT_CAPTURED'},{...market(),sport,event_id:'event_'+i,family:'Alt spread 4.5',state:'NO_MODEL'}]);
  const d=C.validateSnapshot({...fresh(),markets:rows});
  assert.equal(C.summary(d).rows,14);
  assert.equal(C.selectRows(d,{sport:'PGA'}).length,2);
  assert.equal(C.selectRows(d,{state:'NO_MODEL'}).length,7);
});
test('search is case insensitive and searches event, family, reason',()=>{
  const d=C.validateSnapshot({...fresh(),markets:[market(),{...market(),event_id:'e2',event_label:'Different',family:'Passing prop',reason:'Roster lacks proof',state:'NO_INPUTS'}]});
  assert.equal(C.selectRows(d,{query:'first HALF'}).length,1);
  assert.equal(C.selectRows(d,{query:'roster'}).length,1);
  assert.equal(C.selectRows(d,{sport:'NFL'}).length,0);
  assert.equal(C.selectRows(d,{query:'no such event'}).length,0);
});
test('schema version is a strict no-fallback contract',()=>{
  assert.throws(()=>C.validateSnapshot({...fresh(),schema_version:'v0'}),/schema version/);
  assert.throws(()=>C.validateSnapshot({...fresh(),schema_version:undefined}),/schema version/);
});
test('synthetic field is mandatory boolean and never inferred from data',()=>{
  assert.throws(()=>C.validateSnapshot({...fresh(),synthetic:undefined}),/explicitly true or false/);
  assert.throws(()=>C.validateSnapshot({...fresh(),synthetic:'false'}),/explicitly true or false/);
});
test('UTC timestamp must be explicit ISO Z',()=>{
  for(const stamp of ['2026-11-15T10:00:00-06:00','2026-11-15','NaN','2026-11-15T10:00:00','2026-11-15T10:00:00Z extra']){
    assert.throws(()=>C.validateSnapshot({...fresh(),generated_at_utc:stamp}),/UTC ISO/);
  }
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:[{...market(),event_start_utc:'2026-11-15T10:00:00'}]}),/UTC ISO/);
});
test('UTC timestamps reject calendar and clock rollover while preserving valid leap days and precision',()=>{
  for(const stamp of ['2026-02-29T01:00:00Z','2026-02-30T01:00:00Z','2026-04-31T01:00:00.123456Z','2026-11-15T24:00:00Z']){
    assert.throws(()=>C.validateSnapshot({...fresh(),generated_at_utc:stamp}),/generated_at_utc must be a UTC ISO/);
    assert.throws(()=>C.validateSnapshot({...fresh(),markets:[{...market(),event_start_utc:stamp}]}),/event_start_utc must be a UTC ISO/);
  }
  const stamp='2024-02-29T23:59:59.123456Z';
  const d=C.validateSnapshot({...fresh(),generated_at_utc:stamp,markets:[{...market(),event_start_utc:stamp}]});
  assert.equal(d.generated_at_utc,stamp);
  assert.equal(d.markets[0].event_start_utc,stamp);
});
test('unsupported sport is blocked',()=>{
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:[{...market(),sport:'UFC'}]}),/unsupported sport/);
});
test('unrecognized market state cannot silently become official',()=>{
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:[{...market(),state:'VERIFIED'}]}),/unsupported state/);
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:[{...market(),state:'APPROVED'}]}),/unsupported state/);
});
test('provider source cannot claim CONNECTED or VERIFIED',()=>{
  for(const state of ['CONNECTED','VERIFIED','AUTHENTICATED']){
    assert.throws(()=>C.validateSnapshot({...fresh(),sources:[{name:'DK',note:'unverified',state}]}),/non-certified/);
  }
});
test('forbid prices, wagers, secret keys and probabilities on root and market records',()=>{
  for(const key of ['api_key','price_american','model_p','ev','stake_u','official','bet','pick','token']){
    assert.throws(()=>C.validateSnapshot({...fresh(),[key]:'fake'}),/forbidden sensitive or wager field/);
    assert.throws(()=>C.validateSnapshot({...fresh(),markets:[{...market(),[key]:'fake'}]}),/forbidden sensitive or wager field/);
  }
});
test('forbid odds and secret fields in local source registry too',()=>{
  assert.throws(()=>C.validateSnapshot({...fresh(),sources:[{name:'DK',note:'missing',state:'UNVERIFIED',authorization:'Bearer fake'}]}),/forbidden sensitive/);
});
test('invalid rows and missing fields stop the full import instead of dropping cases',()=>{
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:[market(),{...market(),reason:''}]}),/reason/);
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:[market(),null]}),/must be an object/);
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:{}}),/markets must/);
  assert.throws(()=>C.validateSnapshot({...fresh(),sources:[null]}),/must be an object/);
});
test('reject hostile oversized fields but preserve harmless markup literally for textContent rendering',()=>{
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:[{...market(),reason:'x'.repeat(361)}]}),/reason/);
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:[{...market(),event_label:'x'.repeat(141)}]}),/event_label/);
  const x=C.validateSnapshot({...fresh(),markets:[{...market(),reason:'<img src=x onerror=alert(1)>'}]});
  assert.equal(x.markets[0].reason,'<img src=x onerror=alert(1)>');
});
test('strict record caps avoid huge local in-memory table import',()=>{
  assert.throws(()=>C.validateSnapshot({...fresh(),markets:Array(6001).fill(market())}),/at most 6000/);
  assert.throws(()=>C.validateSnapshot({...fresh(),sources:Array(101).fill({name:'X',note:'X',state:'BLOCKED'})}),/at most 100/);
});
test('source-provided approved gate claim is intentionally ignored',()=>{
  const d=C.validateSnapshot({...fresh(),gates:{A:'PASSED',B:'PASSED',C:'PASSED',D:'PASSED',E:'PASSED'}});
  assert.equal(d.independent_verification,false);assert.equal(d.approved_stake_u,0);
  assert.equal(Object.hasOwn(d,'gates'),false);
});
test('code has no network or persistent store dependency',()=>{
  const fs=require('node:fs'); const source=fs.readFileSync(require.resolve('./core.js'),'utf8');
  assert.doesNotMatch(source,/\bfetch\s*\(|\bXMLHttpRequest\b|\blocalStorage\b|\bsessionStorage\b/);
});
