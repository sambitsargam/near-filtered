/* NEAR, Filtered — dashboard renderer.
   Reads data/metrics.json and draws every panel. All displayed values come
   from that file; nothing here invents a number, it only formats them.
   Motion is decoration on top: with html.motion absent (reduced motion, or
   no IntersectionObserver) every element renders in its final state. */

const C = {
  cobalt: "#2F5BFF", cobaltSoft: "#6E8BFF", lime: "#C6FF1A",
  coral: "#FF5C7A", amber: "#FFB020", border: "#1C2130",
  muted: "#8A93A6", faint: "#4A5263", text: "#F2F4F8",
};
const MOTION = document.documentElement.classList.contains("motion");
const CHIP = { REJECTED: "rejected", SUPPORTED: "supported", INCONCLUSIVE: "inconclusive", PENDING: "inconclusive" };
const nf = (x, d = 0) => (+x).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
const pc = (x, d = 1) => nf(x * 100, d) + "%";
const month = (s) => new Date(s + "-15");
const fmtM = d3.utcFormat("%b %y");
const plotStyle = { background: "transparent", color: C.muted, fontFamily: "'JetBrains Mono', monospace", fontSize: "11.5px" };
const W = (el) => Math.max(280, el.clientWidth || 900);
const $ = (id) => document.getElementById(id);

/* ---------- once-only viewport observer ---------- */
const watchers = new Map();
const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    io.unobserve(e.target);
    const fn = watchers.get(e.target); watchers.delete(e.target);
    fn && fn(e.target);
  }
}, { rootMargin: "0px 0px -12% 0px", threshold: 0.08 }) : null;
function onView(el, fn) {
  if (!io || !MOTION) { fn(el); return; }
  watchers.set(el, fn); io.observe(el);
}

/* ---------- charts: render, prime, draw in ---------- */
const charts = [];          // { el, render } — re-run on resize
const played = new WeakSet();

function prime(el) {
  if (!MOTION || played.has(el)) return;
  el.querySelectorAll('g[aria-label="line"] path').forEach((p) => {
    const L = p.getTotalLength(); p.style.strokeDasharray = `${L} ${L}`; p.style.strokeDashoffset = L;
  });
  el.querySelectorAll('g[aria-label="area"] path, g[aria-label="dot"] circle, g[aria-label="text"] text')
    .forEach((n) => { n.style.opacity = 0; });
}
function play(el) {
  if (!MOTION || played.has(el)) return;
  played.add(el);
  const ease = "cubic-bezier(.45,0,.2,1)";
  el.querySelectorAll('g[aria-label="line"] path').forEach((p, i) => {
    const L = +p.style.strokeDashoffset || p.getTotalLength();
    const a = p.animate([{ strokeDashoffset: L }, { strokeDashoffset: 0 }], { duration: 1500, delay: 150 + i * 180, easing: ease, fill: "forwards" });
    a.onfinish = () => { p.style.strokeDasharray = ""; p.style.strokeDashoffset = ""; a.cancel(); };
  });
  el.querySelectorAll('g[aria-label="area"] path').forEach((n) => {
    n.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 1200, delay: 700, fill: "forwards" }).onfinish = () => { n.style.opacity = ""; };
  });
  const dots = [...el.querySelectorAll('g[aria-label="dot"] circle')];
  dots.forEach((n, i) => {
    n.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, delay: 300 + (i % 40) * 90, fill: "forwards" }).onfinish = () => { n.style.opacity = ""; };
  });
  el.querySelectorAll('g[aria-label="text"] text').forEach((n) => {
    n.animate([{ opacity: 0, transform: "translateX(-6px)" }, { opacity: 1, transform: "none" }], { duration: 600, delay: 1500, fill: "forwards" }).onfinish = () => { n.style.opacity = ""; };
  });
}
function chart(el, render) {
  charts.push({ el, render });
  render(); prime(el); onView(el, play);
}
let resizeT;
addEventListener("resize", () => {
  clearTimeout(resizeT);
  resizeT = setTimeout(() => charts.forEach(({ el, render }) => { render(); prime(el); }), 180);
});

function linePlot(el, data, { y, color, yFmt, yLabel, extraMarks = [], height = 300 }) {
  chart(el, () => el.replaceChildren(Plot.plot({
    width: W(el), height, marginLeft: 58, style: plotStyle,
    x: { label: null, tickFormat: fmtM },
    y: { label: yLabel, grid: true, tickFormat: yFmt, zero: true },
    marks: [
      Plot.areaY(data, { x: "m", y, fill: color, fillOpacity: 0.12, curve: "monotone-x" }),
      Plot.lineY(data, { x: "m", y, stroke: color, strokeWidth: 2.5, curve: "monotone-x" }),
      Plot.dot(data, { x: "m", y, fill: color, r: 3.2, stroke: "#05060A", strokeWidth: 1.5 }),
      Plot.ruleY([0], { stroke: C.border }),
      Plot.ruleX(data, Plot.pointerX({ x: "m", stroke: C.faint, strokeDasharray: "2,3" })),
      Plot.dot(data, Plot.pointerX({ x: "m", y, r: 6, fill: color, stroke: "#05060A", strokeWidth: 2 })),
      Plot.tip(data, Plot.pointerX({ x: "m", y, title: (d) => `${d3.utcFormat("%B %Y")(d.m)}\n${d.tipText}`,
        fill: "#11141D", stroke: C.border })),
      ...extraMarks,
    ],
  })));
}

/* ---------- number count-up ---------- */
function countUp(el, target, fmt, dur = 1600) {
  if (!MOTION) { el.textContent = fmt(target); return; }
  el.textContent = "—";
  onView(el, () => {
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 4);
      el.textContent = fmt(k === 1 ? target : target * e);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

/* ---------- sparkline for scoreboard cards ---------- */
function spark(values) {
  const w = 200, h = 44, n = values.length;
  const x = d3.scaleLinear([0, n - 1], [2, w - 4]);
  const y = d3.scaleLinear(d3.extent(values), [h - 4, 4]);
  const line = d3.line((_, i) => x(i), y).curve(d3.curveMonotoneX)(values);
  const area = d3.area((_, i) => x(i), h, y).curve(d3.curveMonotoneX)(values);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <path class="a" d="${area}"/><path class="l" d="${line}" vector-effect="non-scaling-stroke"/>
    <path class="dot" d="M${x(n - 1)},${y(values[n - 1])}h0" vector-effect="non-scaling-stroke"/></svg>`;
}

fetch("data/metrics.json").then((r) => r.json()).then((m) => {
  const h = m.hypotheses, w = m.window, sb = m.scoreboard;

  $("windowline").textContent =
    `window ${w.start} .. ${w.end} · dataset current to ${w.data_latest} · generated ${m.generated_at_utc} · ${m.cost.queries} queries, ${nf(m.cost.gib_billed, 0)} GiB billed`;

  /* ---------- hero ---------- */
  const anchors = { H1: "#h1", H2: "#h2", H3: "#h3", H4: "#signature", H5: "#h5" };
  const HIDS = ["H1", "H2", "H3", "H4", "H5"];
  $("strip").innerHTML = HIDS.map((k) =>
    `<a class="chip ${CHIP[sb[k]]}" href="${anchors[k]}">${k} <b>${h[k].name}</b></a>`).join("");

  const share0 = h.H4.series.settlement_share_count;
  const heroStats = [
    ["coral", h.H1.trend.total_change_pct, (v) => `${nf(v, 1)}%`, "economic accounts, first month to last"],
    ["coral", h.H1.grid_summary.down, (v) => `${nf(v)}/${h.H1.grid_summary.cells}`, "threshold cells where the decline holds"],
    ["lime", share0.at(-1).value, (v) => pc(v, 2), `settled cross-chain via Intents, up from ${pc(share0[0].value, 2)}`],
    ["amber", h.H5.materiality_bar.final_month_value, (v) => pc(v, 2), `burn as a share of issuance, vs a ${pc(h.H5.materiality_bar.threshold, 0)} bar`],
  ];
  $("herostats").innerHTML = heroStats.map(([cls, , , label]) =>
    `<div class="hstat ${cls}"><div class="n">&nbsp;</div><div class="l">${label}</div></div>`).join("");
  [...$("herostats").querySelectorAll(".n")].forEach((el, i) => {
    const [, v, fmt] = heroStats[i];
    setTimeout(() => countUp(el, v, fmt, 1800), MOTION ? 1100 : 0);
  });

  /* ---------- scoreboard ---------- */
  const ones = {
    H1: () => `<strong>${nf(h.H1.trend.total_change_pct, 1)}%</strong> economic accounts; down in <strong>${h.H1.grid_summary.down}/${h.H1.grid_summary.cells}</strong> grid cells`,
    H2: () => `top-10 receiver share <strong>${pc(h.H2.series.top10_share[0].value)} → ${pc(h.H2.series.top10_share.at(-1).value)}</strong>`,
    H3: () => `retention drifts down; the 95% CI spans zero`,
    H4: () => `settlement share <strong>${pc(share0[0].value, 2)} → ${pc(share0.at(-1).value, 2)}</strong>${h.H4.is_partial ? " · provisional" : ""}`,
    H5: () => `burn is <strong>${pc(h.H5.materiality_bar.final_month_value, 2)}</strong> of issuance vs a <strong>${pc(h.H5.materiality_bar.threshold, 0)}</strong> bar`,
  };
  const sparks = {
    H1: h.H1.series.map((d) => d.value),
    H2: h.H2.series.top10_share.map((d) => d.value),
    H3: h.H3.cohorts.filter((c) => c.retained_m3 != null && c.cohort !== h.H3.left_censored_cohort).map((c) => c.retained_m3),
    H4: share0.map((d) => d.value),
    H5: h.H5.series.burn_over_gross_issuance.map((d) => d.value),
  };
  const board = $("board");
  HIDS.forEach((hid, i) => {
    const v = sb[hid];
    const card = document.createElement("a");
    card.className = `card ${CHIP[v]}`; card.href = anchors[hid]; card.style.setProperty("--i", i);
    card.innerHTML = `<span class="top"><span class="hid">${hid}</span>
        <span class="chip ${CHIP[v]}">${v}${h[hid].is_partial ? ` ·${h[hid].months_complete}/${h[hid].months_expected}` : ""}</span></span>
      <span class="hname">${h[hid].name}</span>
      ${sparks[hid].length > 1 ? spark(sparks[hid]) : ""}
      <span class="one">${ones[hid]()}</span>
      <span class="go">see the evidence →</span>`;
    board.appendChild(card);
  });
  onView(board, (el) => el.classList.add("in"));
  if (MOTION && matchMedia("(pointer: fine)").matches) {
    board.querySelectorAll(".card").forEach((card) => {
      card.addEventListener("pointermove", (e) => {
        const r = card.getBoundingClientRect(), px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
        card.style.setProperty("--mx", `${px * 100}%`); card.style.setProperty("--my", `${py * 100}%`);
        card.style.transform = `rotateX(${(0.5 - py) * 8}deg) rotateY(${(px - 0.5) * 10}deg) translateY(-4px)`;
      });
      card.addEventListener("pointerleave", () => { card.style.transform = ""; });
    });
  }

  /* ---------- H4 signature ---------- */
  const share = share0.map((d, i) => ({
    m: month(d.month), v: d.value,
    tipText: `share ${pc(d.value, 2)}\nintents ${nf(h.H4.series.intents_swaps[i].value)} · native ${nf(h.H4.series.native_transfers[i].value)}`,
  }));
  $("h4-vw").textContent = sb.H4 + (h.H4.is_partial ? ` · ${h.H4.months_complete}/${h.H4.months_expected} months` : "");
  $("h4-plain").textContent =
    `Of the settlement events we can see on the same sampled days, the share going through NEAR Intents ` +
    `rose from ${pc(share[0].v, 2)} to ${pc(share.at(-1).v, 2)}. The Intents leg counts 1Click swaps only, so it is a lower bound.`;
  linePlot($("h4-chart"), share, { y: "v", color: C.lime, yLabel: "share of settlement events", yFmt: (d) => pc(d, 0), height: 340 });
  $("h4-source").textContent =
    `Source: Intents Explorer API (1Click) + crypto_near_mainnet_us.ft_events, the same 4 sampled days per month`;
  $("h4-note").textContent =
    `Senders are identifiable on ${pc(h.H4.sender_coverage_mean)} of successful swaps, so unique-swapper counts cover ` +
    `part of the sample. The value form of this metric is not computed: native token coverage would be ` +
    `${nf(h.H4.value_form.native_token_coverage_pct, 0)}%, because the dataset carries no token decimals.`;

  /* decomposition: indexed to 100 */
  const dec = h.H4.series.intents_swaps.map((d, i) => ({
    m: month(d.month),
    intents: (d.value / h.H4.series.intents_swaps[0].value) * 100,
    native: (h.H4.series.native_transfers[i].value / h.H4.series.native_transfers[0].value) * 100,
  }));
  $("h4d-plain").textContent =
    `Intents swaps grew ${nf(h.H4.decomposition.intents_growth_pct, 1)}% while native transfers by economic accounts ` +
    `fell ${nf(Math.abs(h.H4.decomposition.native_growth_pct), 1)}%. A share that rises because its denominator is ` +
    `collapsing is a different claim from one that rises because its numerator is growing — and here it is both.`;
  const dEl = $("h4d-chart");
  const long = dec.flatMap((d) => [{ m: d.m, s: "Intents", v: d.intents }, { m: d.m, s: "native", v: d.native }]);
  chart(dEl, () => dEl.replaceChildren(Plot.plot({
    width: W(dEl), height: 290, marginLeft: 58, marginRight: 68, style: plotStyle,
    x: { label: null, tickFormat: fmtM },
    y: { label: "indexed, first month = 100", grid: true },
    color: { domain: ["Intents", "native"], range: [C.lime, C.cobalt] },
    marks: [
      Plot.ruleY([100], { stroke: C.faint, strokeDasharray: "3,3" }),
      Plot.lineY(long, { x: "m", y: "v", stroke: "s", strokeWidth: 2.5, curve: "monotone-x" }),
      Plot.dot(long, { x: "m", y: "v", fill: "s", r: 2.8 }),
      Plot.text(long.slice(-2), { x: "m", y: "v", text: "s", fill: "s", dx: 10, textAnchor: "start", fontSize: 12 }),
      Plot.tip(long, Plot.pointer({ x: "m", y: "v", title: (d) => `${d.s} · ${d3.utcFormat("%B %Y")(d.m)}\nindex ${nf(d.v, 0)}`, fill: "#11141D", stroke: C.border })),
    ],
  })));

  /* ---------- H1 ---------- */
  const h1s = h.H1.series.map((d) => ({ m: month(d.month), v: d.value, tipText: `${nf(d.value)} accounts` }));
  $("h1-vw").textContent = sb.H1;
  $("h1-plain").textContent =
    `${nf(h.H1.trend.first)} accounts cleared the bot filter in the first month, ${nf(h.H1.trend.last)} in the last — ` +
    `${nf(h.H1.trend.total_change_pct, 1)}% at thresholds d=${h.H1.thresholds.d}, c=${h.H1.thresholds.c}, b=${h.H1.thresholds.b}. ` +
    `The 95% interval on the slope, [${nf(h.H1.trend.ci_low)}, ${nf(h.H1.trend.ci_high)}] accounts per month, does not reach zero.`;
  linePlot($("h1-chart"), h1s, { y: "v", color: C.coral, yLabel: "economic accounts", yFmt: d3.format("~s") });
  $("h1-source").textContent =
    `Source: crypto_near_mainnet_us.transactions + account_changes, block_date ${w.start}..${w.end}`;

  /* ---------- H2 ---------- */
  const top10 = h.H2.series.top10_share.map((d) => ({ m: month(d.month), v: d.value, tipText: `top-10 share ${pc(d.value)}` }));
  const hhi = h.H2.series.hhi.map((d) => ({ m: month(d.month), v: d.value, tipText: `HHI ${nf(d.value, 4)}` }));
  $("h2-vw").textContent = sb.H2;
  $("h2-plain").textContent =
    `Among transactions sent by economic accounts, the share going to the ten busiest receivers rose from ` +
    `${pc(top10[0].v)} to ${pc(top10.at(-1).v)}, and the Herfindahl index rose from ${nf(hhi[0].v, 4)} to ` +
    `${nf(hhi.at(-1).v, 4)}. We predicted both would fall.`;
  linePlot($("h2-chart-a"), top10, { y: "v", color: C.coral, yLabel: "top-10 receiver share", yFmt: (d) => pc(d, 0), height: 260 });
  linePlot($("h2-chart-b"), hhi, { y: "v", color: C.coral, yLabel: "HHI (0-1 scale)", yFmt: (d) => nf(d, 2), height: 260 });
  $("h2-source").textContent =
    `Source: crypto_near_mainnet_us.transactions, receivers of economic accounts' transactions, block_date ${w.start}..${w.end}`;

  /* ---------- H3 ---------- */
  const retention = [];
  for (const c of h.H3.cohorts) {
    for (const [key, label] of [["retained_m1", "+1 month"], ["retained_m3", "+3 months"], ["retained_m6", "+6 months"]]) {
      if (c[key] != null) retention.push({ m: month(c.cohort), offset: label, v: c[key] });
    }
  }
  $("h3-vw").textContent = sb.H3;
  $("h3-plain").textContent =
    `Share of each monthly cohort still economic at exactly +1, +3 and +6 months. The +3 trend across cohorts drifts from ` +
    `${pc(h.H3.trend.first)} to ${pc(h.H3.trend.last)}, but its 95% interval spans zero, so the pre-registered rule reads it as inconclusive.`;
  const h3El = $("h3-chart");
  chart(h3El, () => h3El.replaceChildren(Plot.plot({
    width: W(h3El), height: 300, marginLeft: 58, marginRight: 86, style: plotStyle,
    x: { label: null, tickFormat: fmtM },
    y: { label: "share still economic", grid: true, tickFormat: (d) => pc(d, 0), zero: true },
    color: { domain: ["+1 month", "+3 months", "+6 months"], range: [C.faint, C.amber, C.muted] },
    marks: [
      Plot.lineY(retention, { x: "m", y: "v", stroke: "offset", strokeWidth: 2.25, curve: "monotone-x" }),
      Plot.dot(retention, { x: "m", y: "v", fill: "offset", r: 2.8 }),
      Plot.text(["+1 month", "+3 months", "+6 months"].map((o) => retention.filter((r) => r.offset === o).at(-1)),
        { x: "m", y: "v", text: (d) => d.offset, fill: "offset", dx: 8, textAnchor: "start", fontSize: 11.5 }),
      Plot.ruleY([0], { stroke: C.border }),
      Plot.tip(retention, Plot.pointer({ x: "m", y: "v", title: (d) => `cohort ${d3.utcFormat("%B %Y")(d.m)}\n${d.offset}: ${pc(d.v)}`, fill: "#11141D", stroke: C.border })),
    ],
  })));
  $("h3-note").textContent =
    `The window's first cohort (${h.H3.left_censored_cohort}) is left-censored — every account active that month looks new — ` +
    `and is excluded from the headline trend (amendment A3). The verdict is the same with it included.`;

  /* ---------- H5 ---------- */
  const burn = h.H5.series.burn_over_gross_issuance.map((d) => ({ m: month(d.month), v: d.value, tipText: `burn/issuance ${pc(d.value, 2)}` }));
  const bar = h.H5.materiality_bar.threshold;
  $("h5-vw").textContent = sb.H5;
  $("h5-plain").textContent =
    `Burn and supply are both measured from the chain — no inflation rate is assumed anywhere. The ratio ends at ` +
    `${pc(h.H5.materiality_bar.final_month_value, 2)} against the pre-registered ${pc(bar, 0)} bar, and its trend is down. ` +
    `Measured gross issuance over the window is ${nf(h.H5.totals.measured_annual_issuance_pct, 2)}% of ending supply, which independently matches the documented cap.`;
  linePlot($("h5-chart"), burn, {
    y: "v", color: C.coral, yLabel: "burn / gross issuance", yFmt: (d) => pc(d, 0), height: 300,
    extraMarks: [
      Plot.ruleY([bar], { stroke: C.amber, strokeDasharray: "4,4" }),
      Plot.text([{ m: burn.at(-1).m, v: bar }], { x: "m", y: "v", text: () => `pre-registered bar ${pc(bar, 0)}`, fill: C.amber, dy: -10, textAnchor: "end", fontSize: 11.5 }),
    ],
  });
  $("h5-source").textContent =
    `Source: execution_outcomes.tokens_burnt + transactions.receipt_conversion_tokens_burnt vs Δ blocks.total_supply, ${w.start}..${w.end}`;
  $("h5-note").textContent =
    `H5b, the documentary half: no primary Intents source names any mechanism routing fees to NEAR holders. ` +
    `We pre-committed to reading that null as evidence against.`;

  /* ---------- heatmap ---------- */
  const heat = $("heat");
  const ds = [2, 4, 8], cs = [1, 2, 3], bs = [0, 0.1, 1];
  heat.innerHTML = `<div class="corner"></div>` + bs.map((b) => `<div class="coltag">b ≥ ${b}</div>`).join("");
  let ci = 0;
  for (const d of ds) for (const c of cs) {
    heat.insertAdjacentHTML("beforeend", `<div class="rowtag">d≥${d} c≥${c}</div>`);
    for (const b of bs) {
      const cell = h.H1.grid.find((g) => g.d === d && g.c === c && Math.abs(g.b - b) < 1e-9);
      const cls = cell.direction === "down" ? "against" : cell.direction === "flat" ? "flat" : "with";
      heat.insertAdjacentHTML("beforeend",
        `<div class="cell ${cls}${cell.is_default ? " default-cell" : ""}" style="--i:${ci++}" role="img"
              title="d ≥ ${d}, c ≥ ${c}, b ≥ ${b}${cell.is_default ? " (default)" : ""}"
              aria-label="d ${d} c ${c} b ${b}: ${nf(cell.change_pct, 0)} percent, ${cell.direction}">
           <b>${nf(cell.change_pct, 0)}%</b>${cell.direction}</div>`);
    }
  }
  onView(heat, (el) => el.classList.add("in"));

  /* ---------- exploratory ---------- */
  const ex = m.exploratory;
  $("exp-plain").textContent = ex.reading;
  const stats = [
    ["burn / issuance", pc(ex.burn_over_issuance["2026-03"], 1), pc(ex.burn_over_issuance["2026-04"], 1)],
    ["NEAR burned / month", nf(ex.burned_near["2026-03"]), nf(ex.burned_near["2026-04"])],
    ["economic txs / month", d3.format(".3s")(ex.economic_transactions["2026-03"]), d3.format(".3s")(ex.economic_transactions["2026-04"])],
    ["distinct receivers", d3.format(".3s")(ex.distinct_receivers["2026-03"]), d3.format(".3s")(ex.distinct_receivers["2026-04"])],
    ["top-10 share", pc(ex.top10_share["2026-03"], 1), pc(ex.top10_share["2026-04"], 1)],
  ];
  $("exp-stats").innerHTML = stats.map(([k, a, b]) =>
    `<div class="stat"><div class="k">${k}</div>
       <div class="v"><span class="from">${a}</span><span class="arrow">→</span><span class="to">${b}</span></div>
       <div class="mo"><span>March</span><span>April</span></div></div>`).join("");

  /* ---------- what would change our mind ---------- */
  const changes = [
    [`Economic accounts rising for three consecutive months at default thresholds, robust across the grid`, `H1's rejection was a window artefact; the decline reversed`],
    [`Top-10 share falling back toward its early-window level while account counts hold`, `concentration was a transition, not a trend`],
    [`Burn exceeding the ${pc(bar, 0)} bar in any month`, `H5a's materiality bar met; value accrual becomes arguable`],
    [`A primary source documenting Intents fees reaching NEAR holders`, `H5b's null answered; the claim's second clause becomes testable`],
    [`The settlement share rising while native transfers are flat or growing`, `the shift is numerator-driven — the strong form of the claim`],
  ];
  const mind = $("change-list");
  mind.innerHTML = changes.map(([a, b], i) =>
    `<div class="mind" style="--i:${i}"><span class="if">if we see</span><span class="f">${a}</span><span class="m">${b}</span></div>`).join("");
  onView(mind, (el) => el.classList.add("in"));

  /* ---------- cases, with a focus switcher ---------- */
  const grid = $("casegrid");
  grid.innerHTML = m.cases.cases.map((c, i) => `
    <div class="case ${c.name}" style="--i:${i}" data-case="${c.name}">
      <h4>${c.name}</h4>
      <p class="stance">${c.stance}</p>
      <ul>${c.indicators.map((x) =>
        `<li><b>${x.watch}</b><span class="ok">confirms: ${x.confirms}</span><br><span class="ko">kills: ${x.kills}</span></li>`).join("")}</ul>
    </div>`).join("");
  onView(grid, (el) => el.classList.add("in"));
  const tabs = $("casetabs");
  const colors = { all: C.text, bull: C.lime, base: C.cobaltSoft, bear: C.coral };
  tabs.innerHTML = `<span class="pill" aria-hidden="true"></span>` +
    ["all", ...m.cases.cases.map((c) => c.name)].map((n) =>
      `<button role="tab" data-k="${n}" aria-selected="${n === "all"}">${n}</button>`).join("");
  const pill = tabs.querySelector(".pill");
  const select = (btn) => {
    tabs.querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", b === btn));
    pill.style.width = btn.offsetWidth + "px";
    pill.style.transform = `translateX(${btn.offsetLeft}px)`;
    pill.style.background = colors[btn.dataset.k] || C.text;
    const k = btn.dataset.k;
    grid.classList.toggle("focus", k !== "all");
    grid.querySelectorAll(".case").forEach((c) => c.classList.toggle("on", c.dataset.case === k));
  };
  tabs.addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) select(b); });
  requestAnimationFrame(() => select(tabs.querySelector("button")));
  addEventListener("resize", () => select(tabs.querySelector('[aria-selected="true"]')));

  /* ---------- amendments + provenance ---------- */
  const tl = $("amendments");
  tl.innerHTML = m.amendments.map((a, i) =>
    `<li style="--i:${i}"><div class="tag">${a.id} <span>· ${a.date} · ${a.hypothesis || ""}</span></div><p>${a.change}</p></li>`).join("");
  onView(tl, (el) => el.classList.add("in"));
  $("provenance").textContent =
    `generated ${m.generated_at_utc} · window ${w.start}..${w.end} · ${m.cost.queries} BigQuery queries, ${nf(m.cost.gib_billed, 0)} GiB billed (free tier)`;

  /* ---------- SQL toggles ---------- */
  document.querySelectorAll("pre[data-sql]").forEach(async (pre) => {
    try {
      const res = await fetch(pre.dataset.sql);
      pre.textContent = res.ok ? await res.text() : "SQL file not found: " + pre.dataset.sql;
    } catch { pre.textContent = "SQL unavailable offline"; }
  });

  /* Deep links: the browser's native anchor jump fires before the charts
     exist, so a link to #h1 lands on an empty page. Re-run the jump once
     everything is rendered. */
  if (location.hash) {
    const target = document.querySelector(location.hash);
    if (target) target.scrollIntoView({ behavior: "instant", block: "start" });
  }
}).catch((err) => {
  $("windowline").textContent = "failed to load data/metrics.json — " + err;
});

/* ---------- page chrome: reveal, nav, progress, copy ---------- */
if (MOTION) setTimeout(() => document.documentElement.classList.add("settled"), 2600);
document.querySelectorAll(".reveal").forEach((el) => onView(el, (n) => n.classList.add("in")));

const nav = document.querySelector(".topnav"), bar = $("progress"), totop = $("totop");
let ticking = false;
addEventListener("scroll", () => {
  if (ticking) return; ticking = true;
  requestAnimationFrame(() => {
    const y = scrollY, max = document.documentElement.scrollHeight - innerHeight;
    bar.style.transform = `scaleX(${max > 0 ? y / max : 0})`;
    nav.classList.toggle("scrolled", y > 20);
    totop.classList.toggle("show", y > innerHeight * 1.2);
    ticking = false;
  });
}, { passive: true });

const links = [...document.querySelectorAll("#navlinks a")];
if ("IntersectionObserver" in window) {
  const spy = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) {
      links.forEach((a) => {
        const on = a.getAttribute("href") === "#" + e.target.id;
        a.classList.toggle("active", on);
        if (on) a.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
      });
    }
  }, { rootMargin: "-40% 0px -55% 0px" });
  links.forEach((a) => { const s = document.querySelector(a.getAttribute("href")); if (s) spy.observe(s); });
  spy.observe(document.querySelector(".hero"));   // over the hero, nothing is active
}

$("copy").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  try {
    await navigator.clipboard.writeText("git clone https://github.com/sambitsargam/near-filtered\ncd near-filtered && make verify");
    btn.textContent = "Copied"; btn.classList.add("done");
  } catch { btn.textContent = "Select & copy"; }
  setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1800);
});

/* ---------- hero field: raw traffic hits the filter ----------
   Purely decorative. Dots stream in from the left; at the filter line most
   turn coral and fall away, a few pass through and brighten. It encodes no
   data and draws no numbers. */
(function field() {
  const cv = $("field"); if (!cv) return;
  const ctx = cv.getContext("2d");
  let wv, hv, dpr, gate, parts = [], running = true, mouse = { x: -1e4, y: -1e4 };
  const N = () => Math.round(Math.min(420, (wv * hv) / 3000));
  function size() {
    dpr = Math.min(2, devicePixelRatio || 1);
    wv = cv.clientWidth; hv = cv.clientHeight;
    cv.width = wv * dpr; cv.height = hv * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    gate = wv < 760 ? wv * 0.86 : wv > 1100 ? wv * 0.8 : wv * 0.74;
    while (parts.length < N()) parts.push(spawn(true));
    parts.length = N();
  }
  function spawn(anywhere) {
    return {
      x: anywhere ? Math.random() * wv : -10 - Math.random() * 80,
      y: Math.random() * hv, vx: 0.5 + Math.random() * 1.1, vy: 0,
      r: 0.9 + Math.random() * 1.7, pass: Math.random() < 0.16, state: 0, a: 0.35 + Math.random() * 0.5,
      hue: Math.random() < 0.35 ? C.cobaltSoft : C.lime,
    };
  }
  function drawGate(t) {
    const band = ctx.createLinearGradient(gate - 60, 0, gate + 60, 0);
    band.addColorStop(0, "rgba(198,255,26,0)"); band.addColorStop(0.5, "rgba(198,255,26,0.07)"); band.addColorStop(1, "rgba(198,255,26,0)");
    ctx.fillStyle = band; ctx.fillRect(gate - 60, 0, 120, hv);
    const g = ctx.createLinearGradient(0, 0, 0, hv);
    g.addColorStop(0, "rgba(198,255,26,0)"); g.addColorStop(0.5, "rgba(198,255,26,0.7)"); g.addColorStop(1, "rgba(198,255,26,0)");
    ctx.strokeStyle = g; ctx.lineWidth = 1.25; ctx.setLineDash([5, 6]); ctx.lineDashOffset = -t * 0.03;
    ctx.beginPath(); ctx.moveTo(gate, 0); ctx.lineTo(gate, hv); ctx.stroke(); ctx.setLineDash([]);
    if (wv >= 760) {
      ctx.font = "500 10.5px 'JetBrains Mono', monospace"; ctx.textAlign = "center"; ctx.globalAlpha = 0.85;
      ctx.fillStyle = C.lime; ctx.fillText("BOT FILTER", gate, 96);
      ctx.fillStyle = C.coral; ctx.fillText("bots, farms ↓", gate - 70, hv - 70);
      ctx.fillStyle = C.lime; ctx.fillText("economic →", gate + 70, hv - 70);
      ctx.globalAlpha = 1;
    }
  }
  function frame(t) {
    ctx.clearRect(0, 0, wv, hv);
    drawGate(t || 0);
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      const dx = p.x - mouse.x, dy = p.y - mouse.y, d2 = dx * dx + dy * dy;
      if (d2 < 14400) { const f = (1 - d2 / 14400) * 0.6; p.x += (dx / Math.sqrt(d2 + 1)) * f; p.y += (dy / Math.sqrt(d2 + 1)) * f * 2; }
      if (p.state === 0 && p.x >= gate) p.state = p.pass ? 1 : 2;
      if (p.state === 2) { p.vx *= 0.94; p.vy += 0.05; p.a *= 0.965; }
      if (p.state === 1) { p.vx = Math.min(p.vx * 1.02, 3.4); }
      p.x += p.vx; p.y += p.vy;
      let col = C.faint, alpha = p.a;
      if (p.state === 1) { col = p.hue; alpha = Math.min(1, p.a + 0.4); }
      if (p.state === 2) col = C.coral;
      // keep the left text column calm
      if (p.state === 0 && (wv < 760 || p.x < wv * 0.6)) alpha *= 0.5;
      ctx.globalAlpha = alpha; ctx.fillStyle = col;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.state === 1 ? p.r + 0.4 : p.r, 0, Math.PI * 2); ctx.fill();
      if (p.state === 1) { ctx.globalAlpha = alpha * 0.25; ctx.fillRect(p.x - p.vx * 6, p.y - p.r / 2, p.vx * 6, p.r); }
      if (p.x > wv + 20 || p.y > hv + 20 || p.a < 0.02) parts[i] = spawn(false);
    }
    ctx.globalAlpha = 1;
    if (running && MOTION) requestAnimationFrame(frame);
  }
  size();
  addEventListener("resize", () => { size(); if (!MOTION) still(); });
  cv.parentElement.addEventListener("pointermove", (e) => { const r = cv.getBoundingClientRect(); mouse = { x: e.clientX - r.left, y: e.clientY - r.top }; });
  cv.parentElement.addEventListener("pointerleave", () => { mouse = { x: -1e4, y: -1e4 }; });
  function still() { // reduced motion: one settled frame, no loop
    for (let k = 0; k < 260; k++) { running = false; frame(0); }
  }
  if (!MOTION) { still(); return; }
  const vis = new IntersectionObserver(([e]) => {
    const was = running; running = e.isIntersecting && !document.hidden;
    if (running && !was) requestAnimationFrame(frame);
  });
  vis.observe(cv);
  document.addEventListener("visibilitychange", () => {
    const was = running; running = !document.hidden && cv.getBoundingClientRect().bottom > 0;
    if (running && !was) requestAnimationFrame(frame);
  });
  requestAnimationFrame(frame);
})();
