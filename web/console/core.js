/* SportsEdge Research Console — data contract only. No network, prices, or bets. */
(function (root, factory) {
  const exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  else root.SportsEdgeCore = exported;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const SCHEMA = 'sportsedge-public-research-v1';
  const SPORTS = Object.freeze(['NFL', 'CFB', 'CBB', 'NBA', 'MLB', 'NHL', 'PGA']);
  const STATES = Object.freeze([
    'NOT_OFFERED', 'NOT_CAPTURED', 'NO_MODEL', 'NO_PROVENANCE',
    'NO_INPUTS', 'STALE', 'UNSUPPORTED', 'LIVE_OR_CLOSED',
    'BLOCKED', 'RESEARCH_ONLY', 'UNVERIFIED'
  ]);
  const REASONS = Object.freeze({
    NOT_OFFERED: 'Not offered', NOT_CAPTURED: 'Not captured',
    NO_MODEL: 'No validated model', NO_PROVENANCE: 'No provenance',
    NO_INPUTS: 'Missing inputs', STALE: 'Stale evidence',
    UNSUPPORTED: 'Not supported', LIVE_OR_CLOSED: 'Live / closed',
    BLOCKED: 'Blocked', RESEARCH_ONLY: 'Research only', UNVERIFIED: 'Unverified'
  });
  const FAMILIES = Object.freeze({
    NFL: ['Moneyline', 'Spread', 'Game total', 'Team total', 'Halves / quarters', 'Alternate lines', 'Passing props', 'Rushing props', 'Receiving props', 'TD / first TD / 2+ TD', 'SGP / specials'],
    CFB: ['Moneyline', 'Spread', 'Game total', 'Team total', 'Halves / quarters', 'Alternate lines', 'Player props', 'TD / specials', 'SGP'],
    CBB: ['Moneyline', 'Spread', 'Game total', 'Team total', 'First half', 'Alternate lines', 'Player props', 'First basket / specials', 'SGP'],
    NBA: ['Moneyline', 'Spread', 'Game total', 'Team total', 'Halves / quarters', 'Alternate lines', 'Player props', 'First basket', 'SGP'],
    MLB: ['Moneyline', 'Run line', 'Game total', 'Team total', 'Innings', 'Alternate lines', 'Pitcher props', 'Hitter props', 'Home run / specials', 'SGP'],
    NHL: ['Moneyline', 'Puck line', 'Game total', 'Team total', 'Period markets', 'Alternate lines', 'Skater props', 'Goalie props', 'Goal scorer / specials', 'SGP'],
    PGA: ['Outright', 'First-round leader', 'Top finishes', 'Matchups', 'Round markets', 'Player props / specials']
  });

  function cleanText(value, label, maxLength) {
    if (typeof value !== 'string' || !value.trim() || value.length > maxLength || /[\u0000-\u001F\u007F]/.test(value)) {
      throw new Error(label + ' must be nonempty plain text (max ' + maxLength + ' characters)');
    }
    return value.trim();
  }
  function assertObject(x, label) {
    if (x === null || typeof x !== 'object' || Array.isArray(x)) throw new Error(label + ' must be an object');
  }
  function utc(value, label) {
    const match = typeof value === 'string' && /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d{1,6})?Z$/.exec(value);
    const second = match && new Date(match[1] + 'Z');
    // A Date may normalize out-of-range parts. Compare the whole second, keeping the original fractional precision.
    if (!match || match[0] !== value || !Number.isFinite(second.getTime()) || second.toISOString().slice(0, 19) !== match[1]) {
      throw new Error(label + ' must be a UTC ISO timestamp ending Z');
    }
    return value;
  }
  function rejectForbiddenFields(object, label) {
    assertObject(object, label);
    // The public UI should NEVER be a route to publishing raw odds, credentials or picks.
    const banned = /^(odds|price|price_american|api_?key|token|secret|auth|authorization|raw_?payload|probability|model_p|ev|edge|stake|stake_u|units|approved_stake_units|pick|bet|official)$/i;
    for (const key of Object.keys(object)) {
      if (banned.test(key)) throw new Error(label + ': forbidden sensitive or wager field: ' + key);
    }
  }
  function validateSnapshot(input) {
    assertObject(input, 'snapshot');
    rejectForbiddenFields(input, 'snapshot');
    if (input.schema_version !== SCHEMA) throw new Error('Unsupported snapshot schema version');
    if (typeof input.synthetic !== 'boolean') throw new Error('synthetic must be explicitly true or false');
    const generatedAt = utc(input.generated_at_utc, 'generated_at_utc');
    if (!Array.isArray(input.markets) || input.markets.length > 6000) throw new Error('markets must contain at most 6000 rows');
    const markets = input.markets.map((row, index) => {
      const label = 'markets[' + index + ']';
      rejectForbiddenFields(row, label);
      if (!SPORTS.includes(row.sport)) throw new Error(label + ': unsupported sport');
      if (!STATES.includes(row.state)) throw new Error(label + ': unsupported state');
      const out = {
        sport: row.sport,
        event_id: cleanText(row.event_id, label + '.event_id', 100),
        event_label: cleanText(row.event_label, label + '.event_label', 140),
        family: cleanText(row.family, label + '.family', 90),
        state: row.state,
        reason: cleanText(row.reason, label + '.reason', 360)
      };
      if (row.event_start_utc !== undefined && row.event_start_utc !== null && row.event_start_utc !== '') {
        out.event_start_utc = utc(row.event_start_utc, label + '.event_start_utc');
      } else out.event_start_utc = null;
      return out;
    });
    if (!Array.isArray(input.sources) || input.sources.length > 100) throw new Error('sources must contain at most 100 records');
    const sources = input.sources.map((source, index) => {
      const label = 'sources[' + index + ']';
      rejectForbiddenFields(source, label);
      const state = source.state;
      if (!['NOT_CONNECTED', 'UNVERIFIED', 'RESEARCH_ONLY', 'BLOCKED'].includes(state)) {
        throw new Error(label + ': source status must be non-certified');
      }
      return {
        name: cleanText(source.name, label + '.name', 90),
        state,
        note: cleanText(source.note, label + '.note', 240)
      };
    });
    return Object.freeze({
      schema_version: SCHEMA,
      generated_at_utc: generatedAt,
      synthetic: input.synthetic,
      markets: Object.freeze(markets),
      sources: Object.freeze(sources),
      // We intentionally ignore any input claims that release gates have passed.
      independent_verification: false,
      official_count: 0,
      approved_stake_u: 0
    });
  }
  function summary(snapshot) {
    const states = Object.fromEntries(STATES.map(s => [s, 0]));
    const sports = Object.fromEntries(SPORTS.map(s => [s, 0]));
    if (!snapshot) return {rows: 0, eventCount: 0, states, sports, sourceCount: 0, approved_stake_u: 0};
    const events = new Set();
    for (const m of snapshot.markets) {
      states[m.state] += 1;
      sports[m.sport] += 1;
      events.add(m.sport + '|' + m.event_id);
    }
    return {rows: snapshot.markets.length, eventCount: events.size, states, sports, sourceCount: snapshot.sources.length, approved_stake_u: 0};
  }
  function selectRows(snapshot, options) {
    if (!snapshot) return [];
    const sport = options && options.sport || 'ALL';
    const state = options && options.state || 'ALL';
    const query = (options && options.query || '').trim().toLowerCase();
    return snapshot.markets.filter(m =>
      (sport === 'ALL' || m.sport === sport) &&
      (state === 'ALL' || m.state === state) &&
      (!query || [m.event_label, m.event_id, m.family, m.reason].some(x => x.toLowerCase().includes(query)))
    );
  }
  function demonstration() {
    const games = [
      ['NFL', 'DEMO-NFL-001', 'Sample Away vs Sample Home', '2026-12-01T01:00:00Z'],
      ['CFB', 'DEMO-CFB-001', 'Demo College A vs Demo College B', '2026-12-02T01:00:00Z'],
      ['CBB', 'DEMO-CBB-001', 'Demo College C vs Demo College D', '2026-12-03T01:00:00Z'],
      ['NBA', 'DEMO-NBA-001', 'Demo City A vs Demo City B', '2026-12-04T01:00:00Z'],
      ['MLB', 'DEMO-MLB-001', 'Demo Baseball A vs Demo Baseball B', '2027-04-01T01:00:00Z'],
      ['NHL', 'DEMO-NHL-001', 'Demo Hockey A vs Demo Hockey B', '2026-12-05T01:00:00Z'],
      ['PGA', 'DEMO-PGA-001', 'Demo Golf Event', '2026-12-06T13:00:00Z']
    ];
    const states = ['NO_PROVENANCE', 'NOT_CAPTURED', 'NO_MODEL', 'NO_INPUTS', 'UNSUPPORTED'];
    const markets = [];
    games.forEach(([sport, event_id, event_label, event_start_utc], sportIndex) => {
      FAMILIES[sport].forEach((family, index) => {
        const state = states[(sportIndex + index) % states.length];
        markets.push({sport, event_id, event_label, event_start_utc,
          family, state, reason: 'SYNTHETIC EXAMPLE — ' + REASONS[state].toLowerCase() + '; no real quote or prediction'});
      });
    });
    return validateSnapshot({schema_version: SCHEMA, synthetic: true, generated_at_utc: '2026-11-15T00:00:00Z', markets,
      sources: [
        {name:'DraftKings',state:'NOT_CONNECTED',note:'No authenticated provider connection in this browser'},
        {name:'Independent secondary book',state:'NOT_CONNECTED',note:'No second authenticated source connected'},
        {name:'BestBook.app',state:'UNVERIFIED',note:'Website/link only; no licensed live feed or timestamp proof'},
        {name:'Research model inputs',state:'UNVERIFIED',note:'No source publication-time attestation'}
      ]});
  }
  return Object.freeze({SCHEMA, SPORTS, STATES, REASONS, FAMILIES, validateSnapshot, summary, selectRows, demonstration});
});
