/* ===== live / replay layer (added to docs/dashboard_reference.html by tools/dashboard/build_index.py; the simulator above is unchanged) =====
   mode: 'sim' (the page's own simulator), 'replay' (a recorded real cell streamed by the server) or 'live' (a running demo session). In replay and live `sim` points to a RealFeed, an object with the
   same interface as Sim, so the strip, status line, counters, power meter and the thinking box are drawn by the unchanged code from streamed data. The page always says which mode it is in. */
let mode = 'sim', feed = null, es = null, srv = { ok: false, live: false, errors: 0 }, cellsAll = [], pick = { group: 'eval', scene: 'S1', model: '3B', mgr: 'Governor', block: '', cell: null };
const SIM_SPEEDS_HTML = $('speed').innerHTML;
const REPLAY_SPEEDS = [[0.04, '1 s here = 40 ms of the recording'], [0.1, '1 s here = 100 ms of the recording'], [0.3, '1 s here = 300 ms of the recording'], [1, 'real time (1 s = 1 s)'], [4, '4× faster than real time']];
const MODE_TXT = { sim: 'SIMULATOR', replay: 'REPLAY', live: 'LIVE' };
const GROUPS = [['eval', 'Evaluation (registered, 10 blocks)'], ['eval-discarded', 'Evaluation, discarded block'], ['tuning', 'Tuning'], ['t3b', 'Tuning T3b'], ['t3c', 'Tuning T3c'], ['trial', 'Trials'], ['diag', 'Diagnostics'], ['demo', 'Demos (not registered)']];
const api = (path, body) => fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  .then(r => r.json().then(j => { if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status)); return j; }));
const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), n = s.length; return n % 2 ? s[(n - 1) / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2]); };
const num = v => v !== null && v !== undefined && isFinite(v);

class RealFeed {
  constructor(kind, meta) {
    this.kind = kind; this.meta = meta || {}; this.lag = kind === 'live' ? 120 : 0;
    this.clear();
  }
  clear() {
    this.F = []; this.K = []; this.pw = []; this.smS = []; this.ctrlS = []; this.decS = [];
    this.frames = []; this.queue = []; this.tokens = []; this.tok = null; this.waiting = null;
    this.anchorT = 0; this.anchorWall = performance.now(); this.rate = 0; this.playing = true; this.done = false; this.phase = ''; this.statsMsg = null; this.pace = null; this.dropped = 0;
    this.t = 0; this.nextArr = 0; this.cmd = { clock: 1800, mode: 'aligned', duty: 1, guard: 0 }; this.clock = 1800; this.pending = null; this.status = 'idle'; this.powerNow = 0; this.decision = null; this.lastFrameEnd = -1e9;
  }
  ingest(m) {
    if (m.seek) { const keep = { meta: this.meta, kind: this.kind }; this.clear(); this.meta = keep.meta; }
    const e = m.events || {};
    for (const [a, s, en, late] of e.frames || []) { this.F.push({ arr: a * 1000, start: s * 1000, end: en * 1000, miss: late }); this.lastFrameEnd = Math.max(this.lastFrameEnd, en * 1000); }
    for (const [s, en] of e.tokens || []) this.K.push({ start: s * 1000, end: en * 1000 });
    for (const [t, w] of e.power || []) this.pw.push([t * 1000, w]);
    for (const [t, c] of e.sm || []) this.smS.push([t * 1000, c]);
    for (const [t, md, d, g, c] of e.ctrl || []) this.ctrlS.push([t * 1000, md, d, g, c]);
    for (const d of e.decisions || []) this.decS.push({ ...d, t_ms: d.t_s * 1000 });
    this.anchorT = m.t * 1000; this.anchorWall = performance.now(); this.rate = m.rate || 0; this.playing = m.playing !== false; this.phase = m.phase; this.done = m.phase === 'done';
    this.statsMsg = m.stats || this.statsMsg; this.pace = m.pace || null; this.dropped += m.dropped || 0;
    const cut = this.anchorT - 4000;
    const prune = (a, f) => { let i = 0; while (i < a.length && f(a[i]) < cut) i++; if (i > 0) a.splice(0, i); };
    prune(this.F, x => x.end); prune(this.K, x => x.end); prune(this.pw, x => x[0]); prune(this.smS, x => x[0]); prune(this.ctrlS, x => x[0]); prune(this.decS, x => x.t_ms);
  }
  step() { this.update(); }
  last(arr, now, key) { let r = null; for (const x of arr) { if ((key ? x[key] : x[0]) <= now) r = x; else break; } return r; }
  update() {
    const wall = performance.now();
    const ahead = Math.min(wall - this.anchorWall, 80) * this.rate;                       // chip ms since the last message, capped at 80 wall ms
    const now = this.anchorT + ahead - this.lag;
    this.t = now;
    this.frames = this.F.filter(f => f.end <= now && f.end > now - 250).map(f => ({ arr: f.arr, start: f.start, end: f.end, lat: f.end - f.arr, miss: f.miss }));
    this.queue = this.F.filter(f => f.arr <= now && f.end > now).map(f => ({ arr: f.arr, start: f.start <= now ? f.start : null }));
    this.tokens = this.K.filter(k => k.end <= now && k.end > now - 250);
    const inTok = this.K.find(k => k.start <= now && k.end > now);
    this.tok = inTok ? { start: inTok.start } : null;
    const nxt = this.F.find(f => f.arr > now);
    this.nextArr = nxt ? nxt.arr : (this.pace && this.pace.next !== null && this.pace.next * 1000 > now ? this.pace.next * 1000 : now + P);
    const c = this.last(this.ctrlS, now);
    if (c) { if (c[1] === 1) this.cmd.mode = 'aligned'; else if (c[1] === 0) this.cmd.mode = 'unaligned'; this.cmd.duty = c[2]; this.cmd.guard = c[3]; if (num(c[4])) this.cmd.clock = c[4]; }
    const s = this.last(this.smS, now);
    this.clock = s ? s[1] : this.cmd.clock;
    const w = this.last(this.pw, now); if (w) this.powerNow = w[1];
    this.decision = this.last(this.decS, now, 't_ms') || this.decision;
    const fgA = this.queue.some(q => q.start !== null), bgA = !!this.tok;
    this.status = fgA && bgA ? 'both' : fgA ? 'app' : bgA ? 'llm' : 'idle';
    this.waiting = null;
    if (!bgA) this.waiting = this.cmd.duty <= 0 ? null : this.cmd.mode === 'aligned' ? (this.queue.length ? 'app' : 'nofit') : 'rest';       // inferred from the commanded rule, not logged
  }
  isActive(a) { return this.kind === 'replay' ? this.F.some(f => Math.abs(f.arr - a) < P / 2) : this.lastFrameEnd > this.t + this.lag - 100; }
  needMs() { const m = median(this.K.slice(-8).map(k => k.end - k.start)); return m === null ? tokMs(cfg.model, this.clock) : m; }
  stats() { const s = this.statsMsg || {}; return { missPct: s.miss_pct || 0, tokS: s.tok_s || 0, powerW: s.power_w || 0, frames: s.frames || 0, late: s.late || 0, tokens: s.tokens || 0 }; }
  thinkHtml() {
    const d = this.decision, mg = this.meta.manager || 'Manager';
    if (!d && this.kind === 'replay' && !this.meta.has_predictions) {
      const c = this.cmd, r = c.mode === 'aligned' ? 'chatbot only in the gaps' : 'chatbot in bursts, ' + Math.round(c.duty * 100) + '% of the time';
      return '<b>' + mg + ':</b> commanded ' + CLK(c.clock) + ', ' + r + (c.mode === 'aligned' && c.duty < 1 ? ', throttled to ' + Math.round(c.duty * 100) + '%' : '') + '. The reasoning behind it was not recorded for this run: cells from before the dashboard existed keep only the commanded settings. Demo runs keep the full reasoning.';
    }
    if (!d) return '<b>' + mg + ':</b> no decision has been published yet.';
    const rule =d.mode === 1 ? 'chatbot only in the gaps' : d.mode === 0 ? 'chatbot in bursts, ' + Math.round(d.duty * 100) + '% of the time' : 'chatbot rule unknown';
    if (d.idle === 1 && !num(d.options_checked)) return '<b>' + mg + ':</b> the app has gone idle, so the chatbot can have the whole chip. Commanded: ' + CLK(d.clock_mhz) + ', ' + rule + '.';
    if (!num(d.options_checked)) return '<b>' + mg + ':</b> commanded ' + CLK(d.clock_mhz) + ', ' + rule + '. This manager does not publish a plan.' + (num(d.c_hat_ms) ? ' It estimates the next picture at ' + f1(d.c_hat_ms) + ' ms.' : '');
    return '<b>' + mg + ', thinking ten times a second</b><ol>' +
      '<li>The next picture needs about ' + f1(d.c_hat_ms) + ' ms of work at 1800 MHz.</li>' +
      '<li>I checked ' + d.options_checked + ' options. ' + d.options_safe + ' of them keep the worst picture under ' + f1(d.limit_ms) + ' ms and power under ' + (num(d.power_cap_w) ? f1(d.power_cap_w - (d.power_bias_w || 0)) : '?') + ' W.</li>' +
      (d.options_safe > 0 ? '<li>I picked ' + CLK(d.clock_mhz) + ', ' + rule + '. I expect about ' + f1(d.pred_tok_s) + ' word pieces per second, the worst picture around ' + f1(d.pred_q95_ms) + ' ms, and ' + f1(d.pred_power_w) + ' W.</li>'
        : '<li>None of them is safe, so I run the fastest chip speed and pause the chatbot. Pictures always come first.</li>') +
      (d.extra_margin_ms > 0.05 ? '<li>A picture was late recently, so I am keeping ' + f1(d.extra_margin_ms) + ' ms of extra margin for a while.</li>' : '') +
      (num(d.interference) ? '<li>When both overlap I scale my slowdown prediction by ' + f2(d.interference) + ' (learned from what really happened).</li>' : '') +
      (num(d.power_bias_w) ? '<li>Measured power has been ' + (d.power_bias_w >= 0 ? 'above' : 'below') + ' my prediction by ' + f1(Math.abs(d.power_bias_w)) + ' W; I correct for that.</li>' : '') + '</ol>';
  }
}

function realCfg() {
  const m = feed ? feed.meta : {};
  return { ...BASE, ctrl: 'governor', model: m.model_code || '3b', scene: 'S0', budget: m.budget_w || 60, clock: feed ? Math.round(feed.clock) : 1800, c0: 7 };
}
function renderRealCtlsNote() {
  const box = $('stepctls'); box.hidden = false;
  box.innerHTML = '<div class="hint">These sliders and buttons drive the <b>simulator</b>. You are looking at <b>' + MODE_TXT[mode] + '</b> data from the real laptop, so they are switched off.</div><button class="btn" id="to-sim" type="button">Try this step in the simulator</button>';
  $('to-sim').addEventListener('click', () => setMode('sim'));
}
function restartReal() {
  if (!feed) return;
  $('stepwatch').innerHTML = STEPS[step].watch(cfg);
  paintOutcome(true);
}
let lastOut = 0;
function paintOutcome(force) {
  const ts = performance.now(); if (!force && ts - lastOut < 400) return; lastOut = ts;
  if (!feed) return;
  if (feed.kind === 'replay') {
    const o = (feed.meta.outcome || {}), late = (o.miss_completed ?? o.miss) * 100;
    $('o-lbl').textContent = 'This recorded run (60 s measured window; power from the energy counter):';
    $('o-late').innerHTML = '<span class="' + (late <= 1 ? 'good-t' : 'bad-t') + '">' + (num(late) ? f1(late) : '?') + '%</span><small>late pictures</small>';
    $('o-tok').innerHTML = (num(o.tok_s) ? f1(o.tok_s) : '?') + '<small>word pieces per second</small>';
    $('o-pow').innerHTML = (num(o.power_w) ? f1(o.power_w) : '?') + ' W<small>average power' + (feed.meta.budget_w ? ' (limit ' + feed.meta.budget_w + ' W)' : '') + '</small>';
  } else {
    const s = feed.stats();
    $('o-lbl').textContent = 'So far in this live run:';
    $('o-late').innerHTML = '<span class="' + (s.missPct <= 1 ? 'good-t' : 'bad-t') + '">' + f1(s.missPct) + '%</span><small>late pictures</small>';
    $('o-tok').innerHTML = f1(s.tokS) + '<small>word pieces per second</small>';
    $('o-pow').innerHTML = f1(s.powerW) + ' W<small>average sampled power' + (feed.meta.budget_w ? ' (limit ' + feed.meta.budget_w + ' W)' : '') + '</small>';
  }
}

function modeLine() {
  const m = feed ? feed.meta : {};
  if (mode === 'sim') return 'Simulation built from measurements on the real laptop. Not real hardware.';
  const who = [m.id, m.manager, m.model && m.model + ' model', m.scene && 'scene ' + m.scene, m.budget_w && m.budget_w + ' W'].filter(Boolean).join(' · ');
  if (mode === 'replay') return 'Recorded real run on the RTX 4070 laptop: ' + who + (m.demo ? ' · DEMO, not registered data' : '') + '. Frame start times are reconstructed from the log.';
  if (m.synthetic) return 'SYNTHETIC test feed from tools/dashboard/fake_session.py: no GPU, no hardware. ' + who + '. The real controller runs on made-up frames.';
  return 'Real GPU, live from ' + who + (m.demo ? ' (a demo run, not registered data)' : '') + '. The picture runs about 0.12 s behind so that frames and word pieces in progress can be drawn.';
}
function paintMode() {
  const pill = $('modepill'); pill.textContent = MODE_TXT[mode]; pill.dataset.mode = mode;
  $('banner').dataset.mode = mode; $('banner').textContent = MODE_TXT[mode] + (mode === 'sim' ? ': simulated chip, not real hardware' : mode === 'replay' ? ': a recorded real run' : (feed && feed.meta.synthetic ? ': SYNTHETIC test feed, no GPU' : ': the real GPU, right now'));
  for (const [m, id] of [['live', 'mb-live'], ['replay', 'mb-replay'], ['sim', 'mb-sim']]) $(id).setAttribute('aria-pressed', String(mode === m));
  $('modeline').textContent = modeLine();
  $('replaybar').hidden = mode !== 'replay';
  $('pause').hidden = mode === 'live';
  const sp = $('speed');
  if (mode === 'replay') { sp.innerHTML = REPLAY_SPEEDS.map(([v, l]) => '<option value="' + v + '">' + l + '</option>').join(''); sp.value = '0.1'; }
  else { sp.innerHTML = SIM_SPEEDS_HTML; sp.value = String(speed); }
  $('pause').textContent = mode === 'sim' ? (playing ? 'Pause' : 'Play') : (feed && feed.playing === false ? 'Play' : 'Pause');
  document.title = 'Co-Scheduler Lab · ' + MODE_TXT[mode];
}
function note(msg) { $('modenote').textContent = msg || ''; $('modenote').hidden = !msg; }

function openStream() {
  if (es) return;
  es = new EventSource('/stream');
  es.addEventListener('hello', e => onHello(JSON.parse(e.data)));
  es.addEventListener('reset', () => { if (feed) feed.clear(); });
  es.addEventListener('tick', e => onTick(JSON.parse(e.data)));
  es.addEventListener('end', e => onEnd(JSON.parse(e.data)));
  es.onerror = () => { srv.errors++; if (srv.errors > 6) { note('Lost the connection to the dashboard server.'); backToSim(); } };
}
function closeStream() { if (es) { es.close(); es = null; } }
function backToSim() { closeStream(); mode = 'sim'; feed = null; paintMode(); renderStep(); }
function onHello(d) {
  srv.errors = 0;
  if (!d.meta || d.mode === 'sim') return;
  mode = d.mode; feed = new RealFeed(d.mode, d.meta); sim = feed; cfg = realCfg(); note('');
  paintMode(); renderStep();
  const q = new URLSearchParams(location.search);
  if (mode === 'replay' && q.get('t')) api('/api/replay', { action: 'seek', value: +q.get('t') }).then(() => q.get('pause') ? api('/api/replay', { action: 'pause' }) : null).catch(() => {});
}
function onTick(d) {
  if (!feed) return;
  feed.ingest(d);
  if (mode === 'replay') syncReplayUi(d);
  else paintOutcome(false);
}
function onEnd(d) {
  if (d.mode === 'live') { note('Live session ended (' + d.reason + '). Back to the simulator.'); backToSim(); }
  else note('Replay stopped: ' + d.reason);
}

// ---- replay controls
let seeking = false;
function syncReplayUi(d) {
  const dur = feed.meta.duration || 65, sk = $('seek');
  sk.max = dur; if (!seeking) sk.value = d.t;
  $('seekout').textContent = d.t.toFixed(1) + ' s of ' + dur.toFixed(0) + ' s · ' + (d.phase === 'warm-up' ? 'warm-up (not scored)' : d.phase === 'done' ? 'finished' : 'measured window');
  $('pause').textContent = d.playing && !feed.done ? 'Pause' : (feed.done ? 'Play again' : 'Play');
  if (d.speed !== undefined && document.activeElement !== $('speed')) $('speed').value = String(d.speed);
}
function filtered() {
  return cellsAll.filter(c => c.group === pick.group && (!pick.scene || c.scene === pick.scene) && (!pick.model || c.model === pick.model) && (!pick.mgr || c.manager === pick.mgr) && (pick.block === '' || String(c.block) === pick.block));
}
function fill(id, values, cur, any) {
  const s = $(id), vals = [...new Set(values.filter(v => v !== null && v !== undefined))].sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true }));
  s.innerHTML = (any ? '<option value="">any</option>' : '') + vals.map(v => '<option value="' + v + '">' + v + '</option>').join('');
  s.value = vals.map(String).includes(String(cur)) ? String(cur) : (any ? '' : (vals[0] ?? ''));
  return s.value;
}
function buildPickers() {
  const inG = cellsAll.filter(c => c.group === pick.group);
  $('pk-group').innerHTML = GROUPS.filter(([g]) => cellsAll.some(c => c.group === g)).map(([g, l]) => '<option value="' + g + '">' + l + '</option>').join('');
  $('pk-group').value = pick.group;
  pick.scene = fill('pk-scene', inG.map(c => c.scene), pick.scene, true);
  pick.model = fill('pk-model', inG.map(c => c.model), pick.model, true);
  pick.mgr = fill('pk-mgr', inG.map(c => c.manager), pick.mgr, true);
  pick.block = fill('pk-block', inG.map(c => c.block), pick.block, true);
  const list = filtered();
  $('pk-cell').innerHTML = list.map(c => '<option value="' + c.key + '">' + c.id + ' · ' + (c.budget_w ?? '?') + ' W · ' + (num(c.miss) ? f1(c.miss * 100) : '?') + '% late · ' + (num(c.tok_s) ? f1(c.tok_s) : '?') + ' pieces/s</option>').join('');
  pick.cell = list.length ? (list.some(c => c.key === pick.cell) ? pick.cell : (list.find(c => c.budget_w === 60 && c.block !== null) || list[0]).key) : null;
  if (pick.cell) $('pk-cell').value = pick.cell;
  $('pk-count').textContent = list.length + ' recorded runs match';
}
async function loadCell(key) {
  pick.cell = key;
  await api('/api/source', { mode: 'replay', cell: key, speed: 0.1 });
  openStream();
}
function defaultCell() {
  const c = cellsAll.find(x => x.group === 'eval' && x.scene === 'S1' && x.manager === 'Governor' && x.model === '3B' && x.budget_w === 60) || cellsAll[0];
  return c ? c.key : null;
}
async function setMode(m) {
  if (m === mode) return;
  note('');
  try {
    if (m === 'sim') { if (srv.ok) await api('/api/source', { mode: 'sim' }).catch(() => {}); backToSim(); return; }
    if (!srv.ok) throw new Error('The dashboard server is not running: start  python tools/dashboard/server.py  and open the page from it.');
    if (m === 'replay') { const k = pick.cell || defaultCell(); if (!k) throw new Error('No recorded runs found.'); await loadCell(k); return; }
    if (m === 'live') { await api('/api/source', { mode: 'live' }); openStream(); }
  } catch (e) { note(e.message); }
}
async function pollState() {
  try { const st = await api('/api/state'); srv.ok = true; srv.live = st.live_available; } catch (e) { srv.ok = false; srv.live = false; }
  $('mb-live').disabled = !(srv.ok && srv.live); $('mb-replay').disabled = !srv.ok;
  $('mb-live').title = srv.ok ? (srv.live ? 'Attach to the running demo session' : 'No demo session is running: start python tools/dashboard/demo.py') : 'Start python tools/dashboard/server.py and open the page from it';
  $('mb-replay').title = srv.ok ? 'Play back a recorded real run' : 'Start python tools/dashboard/server.py and open the page from it';
}
async function bootModes() {
  $('mb-live').addEventListener('click', () => setMode('live')); $('mb-replay').addEventListener('click', () => setMode('replay')); $('mb-sim').addEventListener('click', () => setMode('sim'));
  for (const [id, key] of [['pk-group', 'group'], ['pk-scene', 'scene'], ['pk-model', 'model'], ['pk-mgr', 'mgr'], ['pk-block', 'block']]) $(id).addEventListener('change', e => { pick[key] = e.target.value; if (key === 'group') { pick.scene = pick.model = pick.mgr = pick.block = ''; } buildPickers(); });
  $('pk-cell').addEventListener('change', e => { loadCell(e.target.value).catch(x => note(x.message)); });
  $('seek').addEventListener('input', () => { seeking = true; }); $('seek').addEventListener('change', e => { seeking = false; api('/api/replay', { action: 'seek', value: +e.target.value }).catch(x => note(x.message)); });
  document.addEventListener('click', e => {                                           // in replay / live the Pause and Restart buttons talk to the server (capture phase: before the simulator's own handlers)
    const b = e.target.closest && e.target.closest('#pause, #restart');
    if (!b || mode === 'sim') return;
    e.stopImmediatePropagation();
    if (mode !== 'replay') return;
    const act = b.id === 'restart' ? 'restart' : (feed && feed.playing && !feed.done ? 'pause' : 'play');
    api('/api/replay', { action: act }).catch(x => note(x.message));
  }, true);
  $('speed').addEventListener('change', e => { if (mode === 'replay') api('/api/replay', { action: 'speed', value: +e.target.value }).catch(x => note(x.message)); });
  paintMode();
  await pollState();
  if (srv.ok) { try { cellsAll = await api('/api/cells'); buildPickers(); } catch (e) { /* keep going without the picker */ } }
  setInterval(pollState, 2500);
  const q = new URLSearchParams(location.search);
  if (srv.ok && q.get('mode') === 'replay') { const k = q.get('cell') || defaultCell(); if (k) { try { await loadCell(k); } catch (e) { note(e.message); } } }
  else if (srv.ok && srv.live && q.get('mode') !== 'sim') setMode('live');
}
