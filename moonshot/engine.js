/* SportsEdge Football Moonshot Lab — research-only rule replay and retrospective payoffs.
   Source: https://support.draftkings.com/dk/en-us/football-moonshot-overview?id=kb_article_view&sysparm_article=KB0012395
   NOT a DraftKings service or validated predictive model. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.MoonshotEngine = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  const TERMINAL = new Set(['won','lost','void','half_settled','cashed_out']);
  function validNum(n, fallback = 0) { const x=Number(n); return Number.isFinite(x) ? x : fallback; }
  function round2(x) { return Math.round((x + Number.EPSILON) * 100)/100; }
  function init(target=3, stake=10) {
    if (!(Number(target)>0) || !Number.isFinite(+target)) throw new Error('Target must be positive');
    if (!(Number(stake)>0) || !Number.isFinite(+stake)) throw new Error('Stake must be positive');
    return {target:+target, stake:+stake, phase:'waiting', multiplier:0, qualifying_plays:0,
      scoring_events:0, events:[], payout:null, note:'Waiting for a qualifying rush or pass outside the opponent 20'};
  }
  function next(state, event) {
    if (TERMINAL.has(state.phase)) throw new Error('This wager is settled. Reset to start a new round.');
    const e={type:String(event.type||'').trim(),yards:validNum(event.yards),first_down:!!event.first_down,
      touchdown:!!event.touchdown, outside20:event.outside20!==false,
      cashout:validNum(event.cashout), label:String(event.label || '')};
    const s={...state,events:state.events.concat([e])};
    if (e.type==='no_play') { s.note='Nullified play — no change'; return s; }
    if (e.type==='half_end') {
      if (s.phase==='waiting') {s.phase='void';s.payout=s.stake;s.note='No round began — stake returned';}
      else {s.phase='half_settled';s.payout=round2(s.stake*s.multiplier);s.note='End of half/game — paid at current multiplier';}
      return s;
    }
    if (e.type==='cashout') {
      if (s.phase!=='active' || !(e.cashout>=0)) throw new Error('Cashout requires an active round and offered payout');
      s.phase='cashed_out';s.payout=round2(e.cashout);s.note='Accepted offered cashout';return s;
    }
    if (s.phase==='waiting') {
      if (e.type==='incomplete' || e.type==='turnover') {
        s.phase='void';s.payout=s.stake;s.note='Designated failure before round starts — void';return s;
      }
      if ((e.type==='pass'||e.type==='rush') && e.outside20) s.phase='active';
      else { s.note='No eligible round start yet';return s; }
    }
    if (e.type==='incomplete' || e.type==='turnover') {
      s.phase='lost';s.payout=0;s.note='Incomplete pass or offensive turnover ended round';return s;
    }
    // Field goals, special-teams touchdowns count toward scoring bonuses, no base gain.
    let scoreThisEvent = e.type==='field_goal' || e.type==='special_teams_td' ||
      ((e.type==='pass'||e.type==='rush') && e.touchdown);
    if (scoreThisEvent) s.scoring_events++;
    let base=0;
    if (e.type==='pass' || e.type==='rush') {
      s.qualifying_plays++;
      if (e.yards>0) base += .2 + Math.floor(e.yards/10)*.5;
      if (e.first_down) base += .5;
      if (e.touchdown) base += 2;
    } else if (e.type==='penalty_first_down') base+=.5;
    const playDoublings = s.qualifying_plays>=10 ? Math.floor((s.qualifying_plays-10)/5)+1 : 0;
    const scoreDoublings = Math.max(0,s.scoring_events-1);
    const factor=Math.pow(2,playDoublings+scoreDoublings);
    s.multiplier=round2(s.multiplier + base*factor);
    if (s.multiplier>=s.target) {
      s.phase='won';s.payout=round2(s.stake*s.target);
      s.note='Target reached — payout capped at selected target';
    } else s.note=`Active: +${round2(base*factor).toFixed(2)}x this action (bonus ${factor}x)`;
    return s;
  }
  function replay(events,target=3,stake=10) {
    let s=init(target,stake);
    for(const e of events) { if (TERMINAL.has(s.phase)) break; s=next(s,e); }
    return s;
  }
  function parseCsv(text) {
    const lines=String(text).replace(/\r/g,'').split('\n').filter(s=>s.trim() && !s.trim().startsWith('#'));
    if(!lines.length) return [];
    function splitCsv(line){const out=[];let cur='',q=false;for(let i=0;i<line.length;i++){
      const c=line[i];if(c==='"'&&q&&line[i+1]==='"'){cur+='"';i++;}
      else if(c==='"'){q=!q;} else if(c===','&&!q){out.push(cur.trim());cur='';} else cur+=c;
    }if(q) throw Error('Unclosed CSV quote');out.push(cur.trim());return out;}
    const hdr=splitCsv(lines[0]).map(x=>x.toLowerCase());
    for (const key of ['round_id','final_x','end_type']) if(!hdr.includes(key)) throw Error('CSV requires '+key+' column');
    const seen = new Set();
    return lines.slice(1).map((line,ix)=>{
      const cols=splitCsv(line);if(cols.length!==hdr.length) throw Error(`Row ${ix+2}: column count mismatch`);
      const obj=Object.fromEntries(hdr.map((h,i)=>[h,cols[i]]));
      const end_type=obj.end_type.toLowerCase();
      if(!['incomplete','turnover','half_end','void'].includes(end_type)) throw Error(`Row ${ix+2}: invalid end_type`);
      const final_x=+obj.final_x;
      if (!Number.isFinite(final_x)||final_x<0) throw Error(`Row ${ix+2}: invalid final_x`);
      const round_id=obj.round_id.trim();
      if (!round_id || seen.has(round_id)) throw Error(`Row ${ix+2}: duplicate or empty round_id`);
      seen.add(round_id);
      if(end_type==='void' && final_x!==0) throw Error(`Row ${ix+2}: void final_x must be zero`);
      return {...obj,end_type,final_x,round_id};
    });
  }
  function summary(rows,target,stake=1) {
    if(!Array.isArray(rows)||!rows.length) throw Error('Load historical rounds first');
    if(!(target>0)||!(stake>0)) throw Error('Target and stake must be positive');
    let wins=0,voids=0,partials=0,profit=0;
    let gross=0;
    for(const r of rows){
      let payout=0;
      if(r.end_type==='void'){voids++; payout=stake;}
      else if(r.final_x>=target){ wins++; payout=stake*target; }
      else if(r.end_type==='half_end'){partials++; payout=stake*r.final_x;}
      gross+=payout;profit+=payout-stake;
    }
    const settled=rows.length-voids;
    const p=settled ? wins/settled : 0;
    const z=1.96;
    const denom=1+z*z/Math.max(settled,1);
    const centre=(p+z*z/(2*Math.max(settled,1)))/denom;
    const spread=z*Math.sqrt(p*(1-p)/Math.max(settled,1)+z*z/(4*Math.max(settled,1)**2))/denom;
    const games=new Set(rows.map(r=>r.game).filter(Boolean)).size;
    return {target, rounds:rows.length, settled, wins, voids, partials, games,
      hitRate:p, hitCiLow:settled?Math.max(0,centre-spread):null,
      hitCiHigh:settled?Math.min(1,centre+spread):null,
      avgGross:gross/rows.length, historicalRoi:profit/(stake*rows.length),
      breakEvenSimple:1/target,
      // Theoretical replay of *all* rounds, not feasible per-round offers or forward edge.
      readiness:'PAPER / 0u — historical replay only; no validated live win probabilities or per-round quote capture'};
  }
  return {init,next,replay,parseCsv,summary};
});

