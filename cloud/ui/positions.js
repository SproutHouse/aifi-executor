// cloud/ui/positions.js — position cards and the position sheet (spec §7, §9.3). One block (ui/README.md): private
// names stay inside; exports go only through the registries. The Positions tab itself is gone (COMMAND_CENTER_SPEC
// §2.3): its cards now sit in the bot page's Overview › Holding now (bot.js), and its risk and books panels moved there.
//   COMP.positionCard(p, opts?) → html     one position card (opts {first}); a tap opens SHEETS.pos
//   COMP.ladder(p, {mini}?) → html         the R-ladder (mini: 8px track, ticks and bead, no labels)
//   COMP.stopWords(p, {tips}?) → html      "stop 3.2% below · locks in +0.41 R" (or "risks −0.60 R")
//   COMP.fitLadders(root)                  re-lays ladder labels with measured widths after inserting ladders elsewhere
//   SHEETS.pos(id)                         the position sheet (id = pos[].id)
// Words follow §14: open R and % of pot lead, "stop x% below", exposure on a secondary line. Only R and % of pot;
// coin prices appear only in the sheet, captioned as market prices.
{
  const clamp = (v, a, z) => Math.min(z, Math.max(a, v));
  const f2 = v => (+v).toFixed(2);
  const Rs = v => '<span class="' + fmt.cls(v) + '">' + fmt.R(v) + '</span>';
  const pid = p => String(p.id != null ? p.id : (p.c || '?') + '-' + (p.t_in != null ? p.t_in : ''));
  // Distances keep §14's one decimal; a hair above zero reads "less than 0.1%" rather than a false "0.0%".
  const dist = d => { const x = num(d); return x == null ? '—' : x >= 0 && x < 0.05 ? 'less than 0.1%' : fmt.pctu(x, 1); };

  // ------------------------------------------------------------------------------------------ data ---
  function posOf(b) { return b && Array.isArray(b.pos) ? b.pos.filter(isObj) : null; }
  // Closest to its stop first; a missing distance goes last (the push already sorts; this keeps it true).
  function sorted(list) {
    return list.map((p, i) => [p, i]).sort((a, z) => {
      const x = num(a[0].to_stop_pct), y = num(z[0].to_stop_pct);
      if (x == null || y == null) return x == null && y == null ? a[1] - z[1] : x == null ? 1 : -1;
      return x - y || a[1] - z[1];
    }).map(e => e[0]);
  }
  function findPos(id) { const s = sorted(posOf(S.b) || []); const i = s.findIndex(p => pid(p) === String(id)); return { s, i, p: i >= 0 ? s[i] : null }; }
  function stopsOf(p) {
    const st = Array.isArray(p.stops) ? p.stops.filter(s => Array.isArray(s) && num(s[0]) != null && num(s[1]) != null).map(s => [num(s[0]), num(s[1]) / 1000]) : [];
    return st.sort((a, z) => a[0] - z[0]);
  }
  // The stop trail, in R. From E4 the push ships every step. Before it, stops[] is [t_in, −1 R] plus the current stop
  // at the last check, so the steps come from the check log's trail events while the entry is inside its window.
  // gap = index of the one segment whose timing is unknown (drawn dashed), or −1.
  function trailOf(p, b) {
    const st = stopsOf(p), asof = num(p.as_of), tin = num(p.t_in);
    if (!st.length) return null;
    const cur = st[st.length - 1][1], end = Math.max(asof != null ? asof : st[st.length - 1][0], st[st.length - 1][0]);
    const pre = st.length === 1 || (st.length === 2 && asof != null && st[1][0] === asof);
    if (!pre) return { pts: st, end, src: 'e4', gap: -1 };
    const t0 = tin != null ? tin : st[0][0];
    if (st.length === 1) return { pts: [[t0, st[0][1]]], end, src: 'flat', gap: -1 };        // never raised: certain
    const ev = (b && Array.isArray(b.events) ? b.events : []).filter(e => Array.isArray(e) && e[1] === 'trail' && e[2] === p.c && num(e[0]) != null && num(e[7]) != null && e[0] >= t0 && e[0] <= end + 60)
      .map(e => [num(e[0]), num(e[7])]).sort((a, z) => a[0] - z[0]);
    if (!ev.length) return { pts: [[t0, st[0][1]], [end, cur]], end, src: 'ends', gap: 0 };
    // The event log holds 7 days (cap 200, trail events kept first). An entry inside its window has every raise in
    // it; when the cap bit, the window starts at the oldest event kept.
    let oldest = Infinity, n = 0;
    for (const e of b.events) if (Array.isArray(e) && num(e[0]) != null) { oldest = Math.min(oldest, e[0]); n++; }
    const g = isoS(b.gen) != null ? isoS(b.gen) : (clockOf(b) || {}).last_t;
    const win = n >= 200 || g == null ? oldest : Math.min(oldest, g - 7 * 86400);
    const full = t0 >= win - 60;
    const pts = [[t0, st[0][1]]].concat(ev);
    let gap = full ? -1 : 0;
    if (Math.abs(pts[pts.length - 1][1] - cur) > 0.015) { pts.push([end, cur]); if (gap < 0) gap = pts.length - 2; }
    return { pts, end, src: full ? 'log' : 'part', gap, win };
  }
  function raises(pts) { let n = 0; for (let i = 1; i < pts.length; i++) if (pts[i][1] > pts[i - 1][1] + 1e-9) n++; return n; }
  // Bitcoin's weekly and daily at entry, from the check that opened the position (inside the 7-day run window).
  function btcAt(p, b) {
    const t = num(p.t_in); if (t == null) return null;
    let best = null;
    for (const r of runsOf(b)) { const d = Math.abs(r.t - t); if (d <= 1800 && (!best || d < Math.abs(best.t - t))) best = r; }
    if (!best || typeof best.btc !== 'string' || best.btc.length < 2) return null;
    const w = c => c === 'B' ? 'bullish' : c === 'b' ? 'bearish' : 'no reading';
    return 'weekly ' + w(best.btc[0]) + ' · daily ' + w(best.btc[1]);
  }
  function evsOf(p, b) {
    const t0 = num(p.t_in);
    return (b && Array.isArray(b.events) ? b.events : []).filter(e => Array.isArray(e) && e[2] === p.c && num(e[0]) != null && (t0 == null || e[0] >= t0 - 60))
      .sort((a, z) => z[0] - a[0]);
  }

  // ---------------------------------------------------------------------------------------- words ---
  function stopWords(p, o) {
    o = o || {};
    const d = num(p.to_stop_pct), L = num(p.r_lock), T = k => o.tips ? tip(k) : '';
    let a;
    if (d == null) a = 'stop' + T('stop') + ' distance ' + na();
    else if (d < 0) a = '<span class="ps-thru">at or through the stop; checked next cycle</span>' + T('stop');
    else a = 'stop ' + dist(d) + (p.side === 'short' ? ' above' : ' below') + T('stop');
    const z = L == null ? '' : '<span class="ps-nw">' + (fmt.cls(L) === 'neg' ? 'risks ' : 'locks in ') + Rs(L) + T('lockedR') + '</span>';
    return a + (z ? ' · ' + z : '');
  }

  // --------------------------------------------------------------------------------------- ladder ---
  // Domain (§7.1): lo = min(−1.25, r_now − .25), hi = max(2, r_now + .5, r_lock + .5).
  function domain(p) {
    const n = num(p.r_now), l = num(p.r_lock);
    let lo = -1.25, hi = 2;
    if (n != null) { lo = Math.min(lo, n - 0.25); hi = Math.max(hi, n + 0.5); }
    if (l != null) { lo = Math.min(lo, l - 0.25); hi = Math.max(hi, l + 0.5); }
    return [lo, hi];
  }
  // Label rows: t0 sits on the track, t1 above it; b0 under it, b1 below that. Each label takes the first row of its
  // preference list where it clears the labels already there (6px gap); positions are % of the track width.
  function place(items, W) {
    const rows = {};
    for (const it of items) {
      const w = Math.min(it.w, W), x = it.x / 100 * W, L = clamp(x - w / 2, 0, Math.max(0, W - w));
      const got = it.pref.find(r => !(rows[r] || []).some(([a, z]) => L < z + 6 && L + w > a - 6)) || it.pref[it.pref.length - 1];
      (rows[got] = rows[got] || []).push([L, L + w]);
      it.row = got; it.left = W ? L / W * 100 : 0;
    }
    return { rt: rows.t1 ? 2 : 1, rb: rows.b1 ? 2 : 1 };
  }
  function fit(lad) {
    const trk = $('.ps-trk', lad); if (!trk) return;
    const W = trk.clientWidth; if (!W) return;
    const items = $$('.ps-lb', lad).map(el => ({ el, x: Number(el.dataset.x), w: el.offsetWidth, pref: String(el.dataset.pref || 't0').split(',') }));
    const r = place(items, W);
    items.forEach(it => { it.el.dataset.row = it.row; it.el.style.left = f2(it.left) + '%'; });
    lad.style.setProperty('--rt', r.rt); lad.style.setProperty('--rb', r.rb);
  }
  function fitAll(root) { $$('.ps-lad[data-fit]', root || document).forEach(lad => call(fit, lad)); }
  let resizeBound = false, rf = 0;
  function bindResize() {
    if (resizeBound) return; resizeBound = true;
    addEventListener('resize', () => { cancelAnimationFrame(rf); rf = requestAnimationFrame(() => fitAll()); });
  }
  function ladder(p, o) {
    o = o || {};
    const [lo, hi] = domain(p), X = r => +clamp((r - lo) / (hi - lo) * 100, 0, 100).toFixed(2);
    const n = num(p.r_now), l = num(p.r_lock), lc = l == null ? '' : fmt.cls(l);
    let trk = '';
    if (lc === 'pos') trk += '<i class="ps-band ps-lock" style="left:' + X(0) + '%;width:' + f2(X(l) - X(0)) + '%"></i>';
    if (lc === 'neg') trk += '<i class="ps-band ps-atrisk" style="left:' + X(l) + '%;width:' + f2(X(0) - X(l)) + '%"></i>';
    trk += '<i class="ps-tick ps-t1" style="left:' + X(-1) + '%"></i><i class="ps-tick ps-t0" style="left:' + X(0) + '%"></i>';
    if (l != null) trk += '<i class="ps-stopm" style="left:' + X(l) + '%"></i>';
    if (n != null) trk += '<i class="ps-bead" data-ps-bead style="left:' + X(n) + '%"></i>';
    const aria = 'R-ladder: first stop −1 R, entry 0 R' + (l != null ? ', stop ' + fmt.R(l) : '') + (n != null ? ', now ' + fmt.R(n) : ', no mark in this data') + '.';
    const attrs = ' role="img" aria-label="' + esc(aria) + '" data-lo="' + lo + '" data-hi="' + hi + '"';
    if (o.mini) return '<div class="ps-lad ps-mini"' + attrs + '><div class="ps-trk">' + trk + '</div></div>';
    const items = [
      n != null && { t: 'now ' + fmt.R(n), x: X(n), pref: ['t0', 't1'], cls: 'ps-ln' },
      { t: 'first stop', x: X(-1), pref: ['b0', 'b1'], cls: 'ps-lf' },
      { t: 'entry', x: X(0), pref: ['b0', 'b1'], cls: '' },
      l != null && { t: 'stop ' + fmt.R(l), x: X(l), pref: ['t0', 'b0', 't1', 'b1'], cls: 'ps-ls' },
    ].filter(Boolean);
    items.forEach(it => { it.w = it.t.length * 6.2 + 2; });
    const r = place(items, 300);                              // a first guess; after() re-lays with measured widths
    const labs = items.map(it => '<span class="ps-lb ' + it.cls + '" aria-hidden="true" data-row="' + it.row + '" data-x="' + it.x + '" data-pref="' + it.pref.join(',')
      + '" style="left:' + f2(it.left) + '%">' + esc(it.t) + '</span>').join('');
    return '<div class="ps-lad" data-fit' + attrs + ' style="--rt:' + r.rt + ';--rb:' + r.rb + '">' + labs + '<div class="ps-trk">' + trk + '</div></div>';
  }

  // ------------------------------------------------------------------------------------ trail line ---
  function trailHtml(p, b, o) {
    o = o || {};
    const tr = trailOf(p, b);
    if (!tr) return '<div class="ps-tr"><span class="ps-tk">Stop trail</span><span class="ps-tn">' + na() + '</span></div>';
    // In R at the stop price (before costs), like the check log's trail events; the headline's "locks in" is after costs.
    const pts = tr.pts, t0 = pts[0][0], span = Math.max(1, tr.end - t0), vals = pts.map(q => q[1]);
    const lo = Math.min(-1, ...vals), hi = Math.max(0, ...vals), H = o.h || 36;
    const X = t => f2(clamp((t - t0) / span * 100, 0, 100)), Y = v => 3 + (hi - v) / ((hi - lo) || 1) * (H - 6);
    let solid = '', dashed = '';
    for (let i = 1; i < pts.length; i++) {
      const [pt, pv] = pts[i - 1], [t, v] = pts[i];
      if (tr.gap === i - 1) dashed += 'M' + X(pt) + ' ' + f2(Y(pv)) + 'L' + X(t) + ' ' + f2(Y(v));
      else solid += 'M' + X(pt) + ' ' + f2(Y(pv)) + 'H' + X(t) + 'V' + f2(Y(v));
    }
    const last = pts[pts.length - 1];
    if (+X(last[0]) < 100) solid += 'M' + X(last[0]) + ' ' + f2(Y(last[1])) + 'H100';
    let dots = '';
    for (let i = 1; i < pts.length; i++) if (pts[i][1] > pts[i - 1][1] + 1e-9)
      dots += '<i class="ps-dt" style="left:' + X(pts[i][0]) + '%;top:' + f2(Y(pts[i][1]) / H * 100) + '%"></i>';
    const n = raises(pts), cur = last[1];
    const cap = p.kind === 'target' && !n ? 'moves only when a rebalance resizes it'
      : tr.src === 'e4' || tr.src === 'flat' ? (n ? word.plural(n, 'raise') + ' since entry' : 'not raised yet')
      : tr.src === 'log' ? (n ? word.plural(n, 'raise') + ' since entry, from the check log' : 'not raised yet')
      : tr.src === 'part' ? 'raises before ' + fmt.when(tr.win) + ' are not in this data · trail history starts with the engine update'
      : 'raised; when is not recorded · trail history starts with the engine update';
    const aria = 'Stop trail: from ' + fmt.R(pts[0][1]) + ' at entry to ' + fmt.R(cur) + (n ? ', raised ' + word.plural(n, 'time') : ', not raised') + '.';
    return '<div class="ps-tr' + (o.bare ? ' ps-bare' : '') + '">' + (o.bare ? '' : '<span class="ps-tk">Stop trail</span>') + '<div class="ps-sp" role="img" aria-label="' + esc(aria) + '" style="height:' + H + 'px">'
      + '<svg viewBox="0 0 100 ' + H + '" preserveAspectRatio="none" aria-hidden="true"><path class="ps-z" d="M0 ' + f2(Y(0)) + 'H100"/>'
      + (solid ? '<path class="ps-l1" d="' + solid + '"/>' : '') + (dashed ? '<path class="ps-l1 ps-gap" d="' + dashed + '"/>' : '') + '</svg>' + dots + '</div>'
      + '<span class="cap ps-tc">' + esc(cap) + '</span></div>';
  }

  // ------------------------------------------------------------------------------------- the card ---
  function kindPill(p) {
    if (p.kind === 'book') return '<span class="pill">' + (p.side === 'short' ? 'Short leg' : 'Long leg') + ' · long-short book</span>';
    return '<span class="pill' + (p.tier === 'A' ? ' auto' : '') + '">' + esc(cap1(word.kind(p.kind))) + ' · ' + esc(word.tier(p.tier)) + (p.venue === 'spot' ? ' · spot' : '') + '</span>';
  }
  // a spot long (p.venue 'spot', paper): the coin itself, bought with cash; no leverage, no funding
  function levWords(p, lev) { return p.venue === 'spot' ? 'spot, no leverage' : lev == null ? 'leverage —' : fmt.lev(lev) + ' isolated'; }
  function exitsLine(p, first) {
    const d = num(p.to_stop_pct), e = isObj(p.exits) ? p.exits : {};
    // a rebalancer's position: a fixed protective stop (touched, not a close) or a rebalance to 0; never a daily or weekly turn
    if (p.kind === 'book') return '<p class="ps-ex">Exits at a weekly rebalance that leaves it out of the book, on the book brake (a 15% fall of the whole pot from its peak), or at its catastrophic stop' + (d == null ? '' : d < 0 ? ' (at or through it now)' : ' (' + dist(d) + (p.side === 'short' ? ' above)' : ' below)')) + '. Paper only.</p>';
    if (p.kind === 'target') return '<p class="ps-ex">Exits if its protective stop' + (d == null ? '' : d < 0 ? ' (at or through it now)' : ' (' + dist(d) + ' below)') + ' is touched, or when a rebalance takes its target weight to 0.</p>';
    const h4 = d == null ? '' : d < 0 ? ' (at or through it now)' : ' (' + dist(d) + ' below)';
    let s = 'Exits if ' + aBw('a') + ' close falls below the stop' + h4 + ' or the daily or weekly turns.';
    const dd = num(e.d_pct), ww = num(e.w_pct), side = v => v == null ? '—' : v < 0 ? dist(-v) + ' above the mark' : dist(v) + ' below';
    if (dd != null || ww != null) s += ' Daily line ' + side(dd) + ' · weekly line ' + side(ww) + '.';
    else s += ' <span class="ps-na">Daily and weekly distances after the engine update.</span>';
    if (first) s += '<span class="ps-nt1">No fixed target: it rides until the stop or a ' + (bw() === 'daily' ? '' : bw() + ', ') + 'daily or weekly turn.</span>';
    return '<p class="ps-ex">' + s + '</p>';
  }
  function secLine(p) {
    const sz = num(p.size_pct), lev = num(p.lev), rk = num(p.risk_pct);
    return '<p class="ps-sec">Exposure ' + (sz == null ? '—' : fmt.pctu(sz, sz >= 10 ? 0 : 1)) + ' of pot · ' + levWords(p, lev)
      + (p.kind === 'target' || p.kind === 'book' ? '' : ' · only ' + (rk == null ? '—' : fmt.pctu(rk, 2)) + ' of pot at risk at entry') + tip('exposure') + '</p>';
  }
  function body(p, o) {
    o = o || {};
    const b = S.b, n = num(p.r_now), pnl = num(p.pnl_pct), tin = num(p.t_in), asof = num(p.as_of), bars = num(p.bars);
    const held = tin != null && asof != null ? 'held ' + fmt.dur(Math.max(0, asof - tin)) + (bars != null ? ' (' + word.plural(bars, 'bar') + ')' : '') : 'held ' + na(true);
    const marks = asof == null ? '' : n == null ? ' · mark ' + na() : ' · marks at ' + fmt.when(asof);
    return '<div class="ps-hd">' + chip(p.c, asof != null ? asof : undefined) + '<span class="ps-bk">' + esc(p.b || '—') + '</span>' + kindPill(p)
      + (o.sheet ? '' : '<button type="button" class="btn small ghost ps-more" data-pos="' + esc(pid(p)) + '" aria-label="' + esc((p.c || '') + ' position details') + '">Details ›</button>') + '</div>'
      + '<div class="ps-meta">' + held + marks + '</div>'
      + '<div class="ps-hl"><div class="ps-o"><span class="ps-big ' + fmt.cls(n) + '"' + (o.sheet ? '' : ' data-ps-r="' + esc(pid(p)) + '"') + '>' + (n == null ? '—' : fmt.R(n)) + '</span>'
      + '<span class="ps-w">open</span>' + tip('openR') + (n == null ? ' <span class="na">' + MISSING + '</span>' : '') + '</div>'
      + '<div class="ps-p"><span class="ps-pv ' + fmt.cls(pnl) + '">' + (pnl == null ? '—' : fmt.pct(pnl)) + '</span><span class="ps-w">of pot</span></div></div>'
      + '<p class="ps-stop">' + stopWords(p, { tips: o.sheet }) + '</p>'
      + ladder(p) + (o.sheet ? '' : trailHtml(p, b)) + exitsLine(p, o.first) + secLine(p);
  }
  function card(p, o) {
    return '<article class="card ps-card rise" data-pos="' + esc(pid(p)) + '" aria-label="' + esc((p.c || '') + ' position') + '">' + body(p, o) + '</article>';
  }

  // ---------------------------------------------------------------------------------------- sheet ---
  SHEETS.pos = function (id) {
    const b = S.b || {}, f = findPos(id), p = f.p;
    if (!p) return '<h2>Position</h2><div class="empty">This position is not open in the latest data. Closed trades are on <a href="#results">Results</a>.</div>';
    const px = isObj(p.px) ? p.px : {}, h = [], asof = num(p.as_of), tin = num(p.t_in);
    h.push('<h2 class="ps-h2"><span class="ps-coin">' + esc(p.c) + '</span> <span class="ps-h2s">open position</span></h2>');
    h.push('<div class="ps-card ps-sc">' + body(p, { sheet: true, first: true }) + '</div>');
    const F = rows => '<dl class="facts">' + rows.filter(Boolean).map(([k, v]) => '<dt>' + k + '</dt><dd>' + v + '</dd>').join('') + '</dl>';
    const P = v => num(v) == null ? na() : fmt.px(v);
    h.push('<div class="sec"><h3>Prices</h3>' + F([['Entry', P(px.entry)], ['First stop' + tip('firstStop'), P(px.stop0)], ['Current stop', P(px.stop)],
      ['Last mark', num(px.mark) == null ? na() : fmt.px(px.mark) + (asof != null ? ' <span class="sub">at ' + fmt.when(asof) + '</span>' : '')]]) + '<p class="cap">Market prices, not your money.</p></div>');
    const bought = evsOf(p, b).find(e => e[1] === 'bought'), sp = bought && (String(bought[6] || '').match(/stop ([\d.]+)/) || [])[1];
    const bars = num(p.bars), sz = num(p.size_pct), rk = num(p.risk_pct), btc = btcAt(p, b), bk = (Array.isArray(b.books) ? b.books : []).find(x => isObj(x) && x.b === p.b);
    h.push('<div class="sec"><h3>Trade</h3>' + F([
      ['Book', esc(p.b || '—') + (bk && bk.bench ? ' <span class="sub">vs ' + esc(bk.bench) + '</span>' : '')],
      ['Trigger', esc(cap1(word.kind(p.kind, true)))],
      ['Grade', esc(word.tier(p.tier)) + (p.tier === 'A' ? tip('auto') : p.tier === 'B' ? tip('watch') : '')],
      ['Opened', tin == null ? na() : fmt.stamp(tin)],
      ['Held', tin != null && asof != null ? fmt.dur(Math.max(0, asof - tin)) + (bars != null ? ' · ' + word.plural(bars, 'bar') : '') : na()],
      ['Costs so far', num(p.cost_R) == null ? na() : fmt.R(p.cost_R) + ' <span class="sub">' + (p.venue === 'spot' ? 'fees (spot pays no funding)' : 'fees and funding') + '</span>'],
      ['Exposure' + tip('exposure'), sz == null ? na() : fmt.pctu(sz, sz >= 10 ? 0 : 1) + ' of pot · ' + (p.venue === 'spot' ? levWords(p) : num(p.lev) == null ? '—' : fmt.lev(p.lev) + ' isolated')],
      p.kind === 'target' || p.kind === 'book' ? null : ['At risk at entry', rk == null ? na() : fmt.pctu(rk, 2) + ' of pot'],
      ['Stop at entry', sp ? fmt.pctu(sp, 1) + (p.side === 'short' ? ' above' : ' below') : na()],
      ['Bitcoin at entry', btc ? esc(btc) : na()],
    ]) + '</div>');
    const tr = trailOf(p, b);
    if (tr) {
      const pts = tr.pts, steps = [];
      pts.forEach((q, i) => {
        if (i > 0 && Math.abs(q[1] - pts[i - 1][1]) < 1e-9) return;           // an unchanged stop is not a step
        const w = i === 0 ? 'first stop' : q[1] > pts[i - 1][1] ? 'raised to' : 'moved to';
        const when = i > 0 && tr.gap === i - 1 ? 'by ' + fmt.when(q[0]) + ' <span class="sub">(when is not recorded)</span>' : fmt.when(q[0]);
        steps.push('<li><span class="ps-stt">' + when + '</span><span>' + w + ' ' + Rs(q[1]) + '</span></li>');
      });
      h.push('<div class="sec"><h3>Stop trail' + tip('stop') + '</h3>' + trailHtml(p, b, { h: 56, bare: true }) + '<ol class="ps-steps">' + steps.reverse().join('') + '</ol>'
        + '<p class="cap">Stop levels in R at the stop price, before costs; “locks in” above is after costs so far and the estimated exit fee.</p></div>');
    }
    const ev = evsOf(p, b).slice(0, 12);
    if (ev.length) h.push('<div class="sec"><h3>Since entry</h3><ul class="ps-evs">' + ev.map(e => {
      const w = word.event(e); return '<li><span class="ps-eic">' + icon(w.ic) + '</span><span class="ps-evt">' + fmt.when(e[0]) + '</span><span class="ps-evx">' + w.html + '</span></li>';
    }).join('') + '</ul></div>');
    const pv = f.s[f.i - 1], nx = f.s[f.i + 1];
    if (f.s.length > 1) h.push('<div class="pn">' + (pv ? '<button type="button" class="btn small" data-ps-go="' + esc(pid(pv)) + '">‹ ' + esc(pv.c) + '</button>' : '<span></span>')
      + '<span class="sub">' + (f.i + 1) + ' of ' + f.s.length + '</span>'
      + (nx ? '<button type="button" class="btn small" data-ps-go="' + esc(pid(nx)) + '">' + esc(nx.c) + ' ›</button>' : '<span></span>') + '</div>');
    return {
      html: h.join(''),
      after(el) {
        bindResize();
        fitAll(el);
        const go = e => {
          const t = e.target instanceof Element && e.target.closest('[data-ps-go]'); if (!t) return;
          e.preventDefault();
          const id2 = t.dataset.psGo;
          openSheet(SHEETS.pos(id2), { kind: 'pos', arg: id2, replace: true });
        };
        el.addEventListener('click', go);
        return () => el.removeEventListener('click', go);
      },
    };
  };

  // -------------------------------------------------------------------------------------- exports ---
  COMP.positionCard = (p, o) => isObj(p) ? card(p, o) : '';
  COMP.ladder = (p, o) => isObj(p) ? ladder(p, o) : '';
  COMP.stopWords = (p, o) => isObj(p) ? stopWords(p, o) : '';
  COMP.fitLadders = root => { bindResize(); fitAll(root); };
}
