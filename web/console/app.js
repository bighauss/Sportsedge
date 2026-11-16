/* SportsEdge client — local status data only; NEVER live auth, odds or wagering. */
(function () {
  'use strict';
  const core = window.SportsEdgeCore;
  if (!core) return;
  const state = {dataset: null, view: 'overview', sport:'ALL', status:'ALL', query:'', importName:''};
  const $ = id => document.getElementById(id);
  const GATES = [
    ['A', 'Authentic two-source odds', 'Capture + source identity'],
    ['B', 'Point-in-time inputs', 'Published before forecast'],
    ['C', 'Walk-forward calibration', 'Untouched forward evaluation'],
    ['D', 'Independent closing line', 'Matched TAKE / CLOSE receipts'],
    ['E', 'Safety and settlement', 'Approved release + controls']
  ];
  const TOOLS = {
    design: [
      ['21st.dev','React UI inspiration','https://21st.dev','21'],
      ['Designeer','Layouts and visual direction','https://designeer.xyz','D'],
      ['Inspora','Composition and brand ideas','https://inspora.design','I'],
      ['Magic UI','Animations and interface patterns','https://magicui.design','✧'],
      ['Uiverse','Buttons, loaders and controls','https://uiverse.io','U'],
      ['Mobbin','Mobile UX reference library','https://mobbin.com','M'],
      ['React Bits','Interactive React effects','https://reactbits.dev','R']
    ],
    ai: [
      ['Claude','Research and coding partner','https://claude.ai','C'],
      ['remove.bg','Image background cleanup','https://www.remove.bg','✂'],
      ['Perplexity','Web research and source discovery','https://www.perplexity.ai','P'],
      ['Suno','Music creation','https://suno.com','♫'],
      ['Lovart','Graphics and creative ideation','https://www.lovart.ai','L'],
      ['Voicebox','Voice production tools','https://voicebox.sh','V'],
      ['Gemini Notebook','Source-grounded notes (formerly NotebookLM)','https://notebook.google.com','N'],
      ['YouMind','Summaries and knowledge work','https://youmind.com','Y'],
      ['Runway','Video editing and generation','https://runwayml.com','↗'],
      ['Descript','Podcast and audio editing','https://www.descript.com','D'],
      ['HeyGen','Avatar video production','https://www.heygen.com','H'],
      ['Oxylabs MCP','Permissioned web extraction','https://github.com/oxylabs/web-api-mcp','⌘']
    ]
  };

  function element(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function toast(message, error=false) {
    const node = $('toast');
    node.textContent = message;
    node.classList.toggle('error', error);
    node.hidden = false;
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {node.hidden=true;}, 5500);
  }
  function navigate(tab) {
    if (!['overview','markets','sources','toolkit'].includes(tab)) return;
    state.view = tab;
    document.querySelectorAll('[data-tab]').forEach(btn => {
      const active = btn.dataset.tab === tab;
      btn.classList.toggle('active',active);
      if (active) btn.setAttribute('aria-current','page');
      else btn.removeAttribute('aria-current');
    });
    for (const view of ['overview','markets','sources','toolkit']) {
      const node = $('view-'+view);
      node.hidden = view !== tab;
      node.classList.toggle('active',view===tab);
    }
    $('currentView').textContent = ({overview:'Overview',markets:'Market inventory',sources:'Source evidence',toolkit:'AI toolkit'})[tab];
    window.scrollTo({top:0,behavior:'instant'});
  }
  function empty(container, heading, info, buttonLabel, callback) {
    const box = element('div','empty-state');
    box.append(element('div','empty-icon','◇'),element('strong','',heading),element('p','',info));
    if (buttonLabel) {
      const b=element('button','button secondary',buttonLabel);
      b.type='button'; b.addEventListener('click',callback);box.append(b);
    }
    container.replaceChildren(box);
  }
  function metricText(value) {return Number(value).toLocaleString('en-US');}
  function statusPill(status) {
    return element('span','state-pill '+(['NOT_OFFERED','UNSUPPORTED','LIVE_OR_CLOSED'].includes(status)?'dim':''),core.REASONS[status] || status.replace(/_/g,' '));
  }
  function populateStatic() {
    const gateList = $('gateList');
    for (const [letter,name,subtitle] of GATES) {
      const li = element('li');
      const label=element('div');label.append(element('div','gate-name',name),element('div','gate-sub',subtitle));
      li.append(element('span','gate-id',letter),label,element('span','gate-state','NOT CLEARED'));gateList.append(li);
    }
    for (const [section,id] of [['design','designTools'],['ai','aiTools']]) {
      const root=$(id);
      for (const [name,desc,url,glyph] of TOOLS[section]) {
        const link=element('a','tool-card');link.href=url;link.target='_blank';link.rel='noopener noreferrer';
        link.setAttribute('aria-label',name+' — opens external site');
        const copy=element('div');copy.append(element('div','tool-title',name),element('div','tool-desc',desc));
        link.append(element('div','tool-icon',glyph),copy,element('span','tool-external','↗'));root.append(link);
      }
    }
    const sport=$('sportFilter');
    for (const value of ['ALL',...core.SPORTS]) {
      const o=element('option','',value === 'ALL'?'All sports':value);o.value=value;sport.append(o);
    }
    const status=$('stateFilter');
    for (const value of ['ALL',...core.STATES]) {
      const o=element('option','',value === 'ALL'?'All states':core.REASONS[value]);o.value=value;status.append(o);
    }
    const now=new Date();
    $('currentTime').textContent=new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',timeZone:'America/Chicago'}).format(now)+' · CT';
  }
  function renderOverview() {
    const s=core.summary(state.dataset);
    $('kpiRows').textContent=state.dataset?metricText(s.rows):'—';
    $('kpiEvents').textContent=state.dataset?metricText(s.eventCount):'—';
    $('kpiSources').textContent='0';
    const grid=$('sportGrid');grid.replaceChildren();
    for (const sport of core.SPORTS) {
      const node=element('div','sport-card');
      const number=element('div','sport-count',state.dataset?metricText(s.sports[sport]):'—');
      number.append(element('small','',state.dataset?'rows':'no data'));
      node.append(element('div','sport-name',sport),number);grid.append(node);
    }
    const preview=$('previewRows');preview.replaceChildren();
    if (!state.dataset || !state.dataset.markets.length) {
      empty(preview,'No inventory loaded','All 7 sports remain unverified until you import a status-only export.','Explore demonstration',useDemo);
    } else {
      for (const m of state.dataset.markets.slice(0,6)) {
        const row=element('div','preview-row');
        row.append(element('span','sport-token',m.sport),element('span','preview-event',m.event_label),element('span','preview-family',m.family),statusPill(m.state));
        preview.append(row);
      }
    }
  }
  function renderMarkets() {
    const rows=core.selectRows(state.dataset,{sport:state.sport,state:state.status,query:state.query});
    $('rowCounter').textContent=metricText(rows.length);
    $('snapshotMarker').textContent=!state.dataset?'NO DATA LOADED':state.dataset.synthetic?'SYNTHETIC DEMONSTRATION':'LOCAL IMPORT · UNVERIFIED';
    const body=$('marketTable');body.replaceChildren();
    if (rows.length === 0) {
      const tr=element('tr');const cell=element('td','table-empty',!state.dataset?'No snapshot imported. Use Import snapshot or Explore sample data.':'No rows match this filter. No omitted rows have been assumed safe.');
      cell.colSpan=5;tr.append(cell);body.append(tr);return;
    }
    const frag=document.createDocumentFragment();
    for (const row of rows.slice(0,1200)) {
      const tr=element('tr'),event=element('td');
      event.append(element('span','',row.event_label),element('span','event-sub',row.event_id));
      const stateCell=element('td');stateCell.append(statusPill(row.state));
      tr.append(element('td','sport-token',row.sport),event,element('td','',row.family),stateCell,element('td','',row.reason));
      frag.append(tr);
    }
    body.append(frag);
    if(rows.length>1200){
      const tr=element('tr');const cell=element('td','table-empty','Showing first 1,200 rows for display performance. All '+metricText(rows.length)+' rows remain in the count and filter results.');cell.colSpan=5;tr.append(cell);body.append(tr);
    }
  }
  function renderSources() {
    const root=$('sourceList');root.replaceChildren();
    const sources=state.dataset?state.dataset.sources:[
      {name:'DraftKings',state:'NOT_CONNECTED',note:'No live authenticated odds connected to this page'},
      {name:'Independent secondary bookmaker',state:'NOT_CONNECTED',note:'A second logo in one aggregator is not independent provenance'},
      {name:'BestBook.app',state:'UNVERIFIED',note:'Link/reference only — no authorized live feed present'},
      {name:'Model inputs & score reports',state:'UNVERIFIED',note:'Point-in-time release/source evidence not established'}
    ];
    if(sources.length===0){empty(root,'No source details supplied','No registered source is independently verified.');}
    else for (const source of sources){
      const row=element('div','source-row');const info=element('div');
      info.append(element('div','source-name',source.name),element('div','source-note',source.note));
      row.append(info,element('span','source-state',source.state.replaceAll('_',' ')));root.append(row);
    }
    $('snapshotDetails').textContent=state.dataset?('Loaded locally: '+state.importName+' · '+state.dataset.markets.length+' market rows · '+(state.dataset.synthetic?'SYNTHETIC EXAMPLE':'UNVERIFIED IMPORT')+' · generated '+state.dataset.generated_at_utc):'No source file imported.';
  }
  function render() {renderOverview();renderMarkets();renderSources();}
  function useDemo(){state.dataset=core.demonstration();state.importName='Built-in synthetic demonstration';state.query='';state.sport='ALL';state.status='ALL';$('marketQuery').value='';$('sportFilter').value='ALL';$('stateFilter').value='ALL';render();toast('SYNTHETIC EXAMPLE LOADED — no actual games, odds or verified picks.');}
  function importFile(){ $('snapshotInput').click(); }
  function clearData(){state.dataset=null;state.importName='';state.query='';state.sport='ALL';state.status='ALL';$('marketQuery').value='';$('sportFilter').value='ALL';$('stateFilter').value='ALL';$('snapshotInput').value='';render();toast('Local snapshot cleared. No browser storage was used.');}
  async function handleFile(ev){
    const file=ev.target.files && ev.target.files[0]; if(!file)return;
    try {
      if(file.size>2_000_000) throw new Error('Snapshot exceeds 2 MB. Import a sanitized summary, not raw market data.');
      const txt=await file.text();const parsed=JSON.parse(txt);
      const fresh=core.validateSnapshot(parsed);
      state.dataset=fresh;state.importName=file.name;
      state.query='';state.sport='ALL';state.status='ALL';$('marketQuery').value='';$('sportFilter').value='ALL';$('stateFilter').value='ALL';
      render();navigate('markets');
      toast('Local status snapshot loaded ('+fresh.markets.length+' rows). Provider authenticity remains UNVERIFIED.');
    }catch(error){toast('Import blocked: '+(error&&error.message||'invalid JSON'),true);}
    finally{ev.target.value='';}
  }
  function init(){
    populateStatic();render();
    document.querySelectorAll('[data-tab]').forEach(n=>n.addEventListener('click',()=>navigate(n.dataset.tab)));
    document.querySelectorAll('[data-goto]').forEach(n=>n.addEventListener('click',()=>navigate(n.dataset.goto)));
    for(const id of ['importTop','heroImport','sourceImport'])$(id).addEventListener('click',importFile);
    $('snapshotInput').addEventListener('change',handleFile);
    $('loadDemo').addEventListener('click',useDemo);
    $('clearSnapshot').addEventListener('click',clearData);
    $('marketQuery').addEventListener('input',ev=>{state.query=ev.target.value;renderMarkets();});
    $('sportFilter').addEventListener('change',ev=>{state.sport=ev.target.value;renderMarkets();});
    $('stateFilter').addEventListener('change',ev=>{state.status=ev.target.value;renderMarkets();});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);
  else init();
})();
