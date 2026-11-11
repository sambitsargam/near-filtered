/* NEAR, Filtered — dashboard renderer.
   Reads data/metrics.json and draws every panel. All displayed values come
   from that file; nothing here invents a number, it only formats them. */

const C = {
  cobalt: "#2F5BFF", cobaltSoft: "#6E8BFF", lime: "#C6FF1A",
  coral: "#FF5C7A", amber: "#FFB020", border: "#1C2130",
  muted: "#8A93A6", faint: "#4A5263",
};
const CHIP = { REJECTED: "rejected", SUPPORTED: "supported", INCONCLUSIVE: "inconclusive", PENDING: "inconclusive" };
const nf = (x, d = 0) => (+x).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
const pc = (x, d = 1) => nf(x * 100, d) + "%";
const month = (s) => new Date(s + "-15");
const fmtM = d3.utcFormat("%b %y");
const plotStyle = { background: "transparent", color: C.muted, fontFamily: "'JetBrains Mono', monospace", fontSize: "11.5px" };
const W = (el) => Math.max(300, el.clientWidth || 900);

function linePlot(el, data, { y, color, yFmt, yLabel, extraMarks = [], height = 300 }) {
  const chart = Plot.plot({
    width: W(el), height, marginLeft: 58, style: plotStyle,
    x: { label: null, tickFormat: fmtM },
    y: { label: yLabel, grid: true, tickFormat: yFmt, zero: true },
    marks: [
      Plot.areaY(data, { x: "m", y, fill: color, fillOpacity: 0.1, curve: "monotone-x" }),
      Plot.lineY(data, { x: "m", y, stroke: color, strokeWidth: 2.25, curve: "monotone-x" }),
      Plot.dot(data, { x: "m", y, fill: color, r: 3, tip: true,
        title: (d) => `${d3.utcFormat("%B %Y")(d.m)}\n${d.tipText}` }),
      Plot.ruleY([0], { stroke: C.border }),
      ...extraMarks,
    ],
  });
  el.replaceChildren(chart);
}

fetch("data/metrics.json").then((r) => r.json()).then((m) => {
  const h = m.hypotheses, w = m.window;

  document.getElementById("windowline").textContent =
    `window ${w.start} .. ${w.end} · dataset current to ${w.data_latest} · generated ${m.generated_at_utc} · ${m.cost.queries} queries, ${nf(m.cost.gib_billed, 0)} GiB billed`;

  /* ---------- scoreboard ---------- */
  const ones = {
    H1: () => `<strong>${nf(h.H1.trend.total_change_pct, 1)}%</strong> economic accounts; down in <strong>${h.H1.grid_summary.down}/${h.H1.grid_summary.cells}</strong> grid cells`,
    H2: () => `top-10 receiver share <strong>${pc(h.H2.series.top10_share[0].value)} → ${pc(h.H2.series.top10_share.at(-1).value)}</strong>`,
    H3: () => `retention drifts down; the 95% CI spans zero`,
    H4: () => `settlement share <strong>${pc(h.H4.series.settlement_share_count[0].value, 2)} → ${pc(h.H4.series.settlement_share_count.at(-1).value, 2)}</strong>${h.H4.is_partial ? " · provisional" : ""}`,
    H5: () => `burn is <strong>${pc(h.H5.materiality_bar.final_month_value, 2)}</strong> of issuance vs a <strong>${pc(h.H5.materiality_bar.threshold, 0)}</strong> bar`,
  };
  const anchors = { H1: "#h1", H2: "#h2", H3: "#h3", H4: "#signature", H5: "#h5" };
  const board = document.getElementById("board");
  for (const hid of ["H1", "H2", "H3", "H4", "H5"]) {
    const v = m.scoreboard[hid];
    const card = document.createElement("a");
    card.className = "card"; card.href = anchors[hid];
    card.innerHTML = `<span class="hid">${hid}</span><span class="hname">${h[hid].name}</span>
      <span class="chip ${CHIP[v]}">${v}${h[hid].is_partial ? ` ·${h[hid].months_complete}/${h[hid].months_expected}` : ""}</span>
      <span class="one">${ones[hid]()}</span>`;
    board.appendChild(card);
  }

  /* ---------- H4 signature ---------- */
  const share = h.H4.series.settlement_share_count.map((d, i) => ({
    m: month(d.month), v: d.value,
    tipText: `share ${pc(d.value, 2)}\nintents ${nf(h.H4.series.intents_swaps[i].value)} · native ${nf(h.H4.series.native_transfers[i].value)}`,
  }));
  document.getElementById("h4-vw").textContent = m.scoreboard.H4 + (h.H4.is_partial ? ` · ${h.H4.months_complete}/${h.H4.months_expected} months` : "");
  document.getElementById("h4-plain").textContent =
    `Of the settlement events we can see on the same sampled days, the share going through NEAR Intents ` +
    `rose from ${pc(share[0].v, 2)} to ${pc(share.at(-1).v, 2)}. The Intents leg counts 1Click swaps only, so it is a lower bound.`;
  linePlot(document.getElementById("h4-chart"), share, {
    y: "v", color: C.lime, yLabel: "share of settlement events",
    yFmt: (d) => pc(d, 0), height: 330,
  });
  document.getElementById("h4-source").textContent =
    `Source: Intents Explorer API (1Click) + crypto_near_mainnet_us.ft_events, the same 4 sampled days per month`;
  document.getElementById("h4-note").textContent =
    `Senders are identifiable on ${pc(h.H4.sender_coverage_mean)} of successful swaps, so unique-swapper counts cover ` +
    `part of the sample. The value form of this metric is not computed: native token coverage would be ` +
    `${nf(h.H4.value_form.native_token_coverage_pct, 0)}%, because the dataset carries no token decimals.`;

  /* decomposition: indexed to 100 */
  const dec = h.H4.series.intents_swaps.map((d, i) => ({
    m: month(d.month),
    intents: (d.value / h.H4.series.intents_swaps[0].value) * 100,
    native: (h.H4.series.native_transfers[i].value / h.H4.series.native_transfers[0].value) * 100,
  }));
  document.getElementById("h4d-plain").textContent =
    `Intents swaps grew ${nf(h.H4.decomposition.intents_growth_pct, 1)}% while native transfers by economic accounts ` +
    `fell ${nf(Math.abs(h.H4.decomposition.native_growth_pct), 1)}%. A share that rises because its denominator is ` +
    `collapsing is a different claim from one that rises because its numerator is growing — and here it is both.`;
  const dEl = document.getElementById("h4d-chart");
  dEl.replaceChildren(Plot.plot({
    width: W(dEl), height: 280, marginLeft: 58, style: plotStyle,
    x: { label: null, tickFormat: fmtM },
    y: { label: "indexed, first month = 100", grid: true },
    marks: [
      Plot.ruleY([100], { stroke: C.border }),
      Plot.lineY(dec, { x: "m", y: "intents", stroke: C.lime, strokeWidth: 2.25, curve: "monotone-x" }),
      Plot.lineY(dec, { x: "m", y: "native", stroke: C.cobalt, strokeWidth: 2.25, curve: "monotone-x" }),
      Plot.text([dec.at(-1)], { x: "m", y: "intents", text: () => "Intents", fill: C.lime, dx: 8, textAnchor: "start", fontSize: 12 }),
      Plot.text([dec.at(-1)], { x: "m", y: "native", text: () => "native", fill: C.cobaltSoft, dx: 8, textAnchor: "start", fontSize: 12 }),
      Plot.dot(dec, { x: "m", y: "intents", fill: C.lime, r: 2.5, tip: true, title: (d) => `Intents: ${nf(d.intents, 0)}` }),
      Plot.dot(dec, { x: "m", y: "native", fill: C.cobalt, r: 2.5, tip: true, title: (d) => `native: ${nf(d.native, 0)}` }),
    ],
    marginRight: 64,
  }));

  /* ---------- H1 ---------- */
  const h1s = h.H1.series.map((d) => ({ m: month(d.month), v: d.value, tipText: `${nf(d.value)} accounts` }));
  document.getElementById("h1-vw").textContent = m.scoreboard.H1;
  document.getElementById("h1-plain").textContent =
    `${nf(h.H1.trend.first)} accounts cleared the bot filter in the first month, ${nf(h.H1.trend.last)} in the last — ` +
    `${nf(h.H1.trend.total_change_pct, 1)}% at thresholds d=${h.H1.thresholds.d}, c=${h.H1.thresholds.c}, b=${h.H1.thresholds.b}. ` +
    `The 95% interval on the slope, [${nf(h.H1.trend.ci_low)}, ${nf(h.H1.trend.ci_high)}] accounts per month, does not reach zero.`;
  linePlot(document.getElementById("h1-chart"), h1s, {
    y: "v", color: C.cobalt, yLabel: "economic accounts", yFmt: d3.format("~s"),
  });
  document.getElementById("h1-source").textContent =
    `Source: crypto_near_mainnet_us.transactions + account_changes, block_date ${w.start}..${w.end}`;

  /* ---------- H2 ---------- */
  const top10 = h.H2.series.top10_share.map((d) => ({ m: month(d.month), v: d.value, tipText: `top-10 share ${pc(d.value)}` }));
  const hhi = h.H2.series.hhi.map((d) => ({ m: month(d.month), v: d.value, tipText: `HHI ${nf(d.value, 4)}` }));
  document.getElementById("h2-vw").textContent = m.scoreboard.H2;
  document.getElementById("h2-plain").textContent =
    `Among transactions sent by economic accounts, the share going to the ten busiest receivers rose from ` +
    `${pc(top10[0].v)} to ${pc(top10.at(-1).v)}, and the Herfindahl index rose from ${nf(hhi[0].v, 4)} to ` +
    `${nf(hhi.at(-1).v, 4)}. We predicted both would fall.`;
  linePlot(document.getElementById("h2-chart-a"), top10, { y: "v", color: C.coral, yLabel: "top-10 receiver share", yFmt: (d) => pc(d, 0), height: 260 });
  linePlot(document.getElementById("h2-chart-b"), hhi, { y: "v", color: C.coral, yLabel: "HHI (0-1 scale)", yFmt: (d) => nf(d, 2), height: 260 });
  document.getElementById("h2-source").textContent =
    `Source: crypto_near_mainnet_us.transactions, receivers of economic accounts' transactions, block_date ${w.start}..${w.end}`;

  /* ---------- H3 ---------- */
  const cohorts = h.H3.cohorts.filter((c) => c.retained_m1 != null);
  const retention = [];
  for (const c of h.H3.cohorts) {
    for (const [key, label] of [["retained_m1", "+1 month"], ["retained_m3", "+3 months"], ["retained_m6", "+6 months"]]) {
      if (c[key] != null) retention.push({ m: month(c.cohort), offset: label, v: c[key] });
    }
  }
  document.getElementById("h3-vw").textContent = m.scoreboard.H3;
  document.getElementById("h3-plain").textContent =
    `Share of each monthly cohort still economic at exactly +1, +3 and +6 months. The +3 trend across cohorts drifts from ` +
    `${pc(h.H3.trend.first)} to ${pc(h.H3.trend.last)}, but its 95% interval spans zero, so the pre-registered rule reads it as inconclusive.`;
  const h3El = document.getElementById("h3-chart");
  h3El.replaceChildren(Plot.plot({
    width: W(h3El), height: 300, marginLeft: 58, marginRight: 86, style: plotStyle,
    x: { label: null, tickFormat: fmtM },
    y: { label: "share still economic", grid: true, tickFormat: (d) => pc(d, 0), zero: true },
    color: { domain: ["+1 month", "+3 months", "+6 months"], range: [C.faint, C.cobalt, C.muted] },
    marks: [
      Plot.lineY(retention, { x: "m", y: "v", stroke: "offset", strokeWidth: (d) => 2, curve: "monotone-x" }),
      Plot.dot(retention, { x: "m", y: "v", fill: "offset", r: 2.5, tip: true, title: (d) => `${d.offset}: ${pc(d.v)}` }),
      Plot.text(["+1 month", "+3 months", "+6 months"].map((o) => retention.filter((r) => r.offset === o).at(-1)),
        { x: "m", y: "v", text: (d) => d.offset, fill: "offset", dx: 8, textAnchor: "start", fontSize: 11.5 }),
      Plot.ruleY([0], { stroke: C.border }),
    ],
  }));
  document.getElementById("h3-note").textContent =
    `The window's first cohort (${h.H3.left_censored_cohort}) is left-censored — every account active that month looks new — ` +
    `and is excluded from the headline trend (amendment A3). The verdict is the same with it included.`;

  /* ---------- H5 ---------- */
  const burn = h.H5.series.burn_over_gross_issuance.map((d) => ({ m: month(d.month), v: d.value, tipText: `burn/issuance ${pc(d.value, 2)}` }));
  const bar = h.H5.materiality_bar.threshold;
  document.getElementById("h5-vw").textContent = m.scoreboard.H5;
  document.getElementById("h5-plain").textContent =
    `Burn and supply are both measured from the chain — no inflation rate is assumed anywhere. The ratio ends at ` +
    `${pc(h.H5.materiality_bar.final_month_value, 2)} against the pre-registered ${pc(bar, 0)} bar, and its trend is down. ` +
    `Measured gross issuance over the window is ${nf(h.H5.totals.measured_annual_issuance_pct, 2)}% of ending supply, which independently matches the documented cap.`;
  linePlot(document.getElementById("h5-chart"), burn, {
    y: "v", color: C.coral, yLabel: "burn / gross issuance", yFmt: (d) => pc(d, 0), height: 300,
    extraMarks: [
      Plot.ruleY([bar], { stroke: C.amber, strokeDasharray: "4,4" }),
      Plot.text([{ m: burn.at(-1).m, v: bar }], { x: "m", y: "v", text: () => `pre-registered bar ${pc(bar, 0)}`, fill: C.amber, dy: -10, textAnchor: "end", fontSize: 11.5 }),
    ],
  });
  document.getElementById("h5-source").textContent =
    `Source: execution_outcomes.tokens_burnt + transactions.receipt_conversion_tokens_burnt vs Δ blocks.total_supply, ${w.start}..${w.end}`;
  document.getElementById("h5-note").textContent =
    `H5b, the documentary half: no primary Intents source names any mechanism routing fees to NEAR holders. ` +
    `We pre-committed to reading that null as evidence against.`;

  /* ---------- heatmap ---------- */
  const heat = document.getElementById("heat");
  const ds = [2, 4, 8], cs = [1, 2, 3], bs = [0, 0.1, 1];
  heat.innerHTML = `<div class="corner"></div>` + bs.map((b) => `<div class="coltag">b ≥ ${b}</div>`).join("");
  for (const d of ds) for (const c of cs) {
    heat.insertAdjacentHTML("beforeend", `<div class="rowtag">d≥${d} c≥${c}</div>`);
    for (const b of bs) {
      const cell = h.H1.grid.find((g) => g.d === d && g.c === c && Math.abs(g.b - b) < 1e-9);
      const cls = cell.direction === "down" ? "against" : cell.direction === "flat" ? "flat" : "with";
      heat.insertAdjacentHTML("beforeend",
        `<div class="cell ${cls}${cell.is_default ? " default-cell" : ""}" role="img"
              aria-label="d ${d} c ${c} b ${b}: ${nf(cell.change_pct, 0)} percent, ${cell.direction}">
           <b>${nf(cell.change_pct, 0)}%</b>${cell.direction === "flat" ? "flat" : cell.direction}</div>`);
    }
  }

  /* ---------- exploratory ---------- */
  const ex = m.exploratory;
  document.getElementById("exp-plain").textContent = ex.reading;
  const stats = [
    ["burn / issuance", pc(ex.burn_over_issuance["2026-03"], 1), pc(ex.burn_over_issuance["2026-04"], 1)],
    ["NEAR burned / month", nf(ex.burned_near["2026-03"]), nf(ex.burned_near["2026-04"])],
    ["economic txs / month", d3.format(".3s")(ex.economic_transactions["2026-03"]), d3.format(".3s")(ex.economic_transactions["2026-04"])],
    ["distinct receivers", d3.format(".3s")(ex.distinct_receivers["2026-03"]), d3.format(".3s")(ex.distinct_receivers["2026-04"])],
    ["top-10 share", pc(ex.top10_share["2026-03"], 1), pc(ex.top10_share["2026-04"], 1)],
  ];
  document.getElementById("exp-stats").innerHTML = stats.map(([k, a, b]) =>
    `<div class="stat"><div class="k">${k}</div><div class="v"><span class="dim">Mar</span> ${a} <span class="dim">→ Apr</span> ${b}</div></div>`).join("");

  /* ---------- what would change our mind ---------- */
  const changes = [
    [`Economic accounts rising for three consecutive months at default thresholds, robust across the grid`, `H1's rejection was a window artefact; the decline reversed`],
    [`Top-10 share falling back toward its early-window level while account counts hold`, `concentration was a transition, not a trend`],
    [`Burn exceeding the ${pc(bar, 0)} bar in any month`, `H5a's materiality bar met; value accrual becomes arguable`],
    [`A primary source documenting Intents fees reaching NEAR holders`, `H5b's null answered; the claim's second clause becomes testable`],
    [`The settlement share rising while native transfers are flat or growing`, `the shift is numerator-driven — the strong form of the claim`],
  ];
  document.querySelector("#change-table tbody").innerHTML =
    changes.map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join("");

  /* ---------- cases ---------- */
  document.getElementById("cases").innerHTML = m.cases.cases.map((c) => `
    <div class="case ${c.name}">
      <h4>${c.name}</h4>
      <p class="stance">${c.stance}</p>
      <ul>${c.indicators.map((i) =>
        `<li><b>${i.watch}</b><br>confirms: ${i.confirms}<br>kills: ${i.kills}</li>`).join("")}</ul>
    </div>`).join("");

  /* ---------- amendments + provenance ---------- */
  document.querySelector("#amendments tbody").innerHTML = m.amendments.map((a) =>
    `<tr><td>${a.id} · ${a.date}</td><td>${a.change}</td></tr>`).join("");
  document.getElementById("provenance").textContent =
    `generated ${m.generated_at_utc} · window ${w.start}..${w.end} · ${m.cost.queries} BigQuery queries, ${nf(m.cost.gib_billed, 0)} GiB billed (free tier)`;

  /* ---------- SQL toggles ---------- */
  document.querySelectorAll("pre[data-sql]").forEach(async (pre) => {
    try {
      const res = await fetch(pre.dataset.sql);
      pre.textContent = res.ok ? await res.text() : "SQL file not found: " + pre.dataset.sql;
    } catch { pre.textContent = "SQL unavailable offline"; }
  });

}).catch((err) => {
  document.getElementById("windowline").textContent = "failed to load data/metrics.json — " + err;
});
