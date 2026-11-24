"use strict";

const UNITS = {
  price_t: { label: "Kč/t", digits: 0 },
  price_bag: { label: "Kč/pytel", digits: 0 },
  price_kg: { label: "Kč/kg", digits: 2 },
};
let unit = "price_t";
let DATA = null;
const charts = {};

const fmt = (v, d) => v.toLocaleString("cs-CZ", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtDate = (iso) => new Date(iso).toLocaleDateString("cs-CZ");
const cssVar = (name) => getComputedStyle(document.querySelector(".viz-root")).getPropertyValue(name).trim();

function label(id) {
  const src = DATA.sources[id];
  const last = DATA.rows.filter((r) => r.source_id === id).pop();
  return `${src.shop} (${last ? last.pack : src.pack})`;
}

function daysBefore(iso, n) {
  const d = new Date(iso);
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function render() {
  const root = document.getElementById("products");
  root.innerHTML = "";
  const u = UNITS[unit];

  for (const [pid, pname] of Object.entries(DATA.products)) {
    // Barvy podle pořadí zdroje v sources.json – stabilní pro daného prodejce.
    const srcIds = Object.keys(DATA.sources).filter((id) => DATA.sources[id].product === pid);
    const color = {};
    srcIds.forEach((id, i) => (color[id] = cssVar(`--series-${(i % 8) + 1}`)));

    const rows = DATA.rows.filter((r) => r.product === pid);
    const dates = [...new Set(rows.map((r) => r.date))].sort();
    const lastDate = dates[dates.length - 1];

    const latest = srcIds
      .map((id) => {
        const hist = rows.filter((r) => r.source_id === id).sort((a, b) => a.date.localeCompare(b.date));
        if (!hist.length) return null;
        const cur = hist[hist.length - 1];
        const ref = (n) => {
          const cut = daysBefore(cur.date, n);
          const old = hist.filter((r) => r.date <= cut);
          return old.length ? old[old.length - 1] : null;
        };
        return { id, cur, w: ref(7), m: ref(30), hist };
      })
      .filter(Boolean)
      .sort((a, b) => a.cur[unit] - b.cur[unit]);

    const sec = document.createElement("section");
    sec.className = "product";
    const best = latest[0];
    const bestDelivered = latest.find((l) => l.cur.delivery_included);
    sec.innerHTML = `
      <h2>${pname}</h2>
      <div class="best">
        ${best ? `<div><div class="label">Nejlevnější teď</div>
          <div class="value">${fmt(best.cur[unit], u.digits)} ${u.label}</div>
          <div class="sub">${label(best.id)}</div></div>` : "<p>Zatím žádná data.</p>"}
        ${bestDelivered ? `<div><div class="label">Nejlevnější s dopravou v ceně</div>
          <div class="value">${fmt(bestDelivered.cur[unit], u.digits)} ${u.label}</div>
          <div class="sub">${label(bestDelivered.id)}</div></div>` : ""}
      </div>
      <div class="chart-wrap"><canvas aria-label="Vývoj ceny ${pname} v ${u.label}" role="img"></canvas></div>
      <div class="table-scroll"><table>
        <thead><tr><th>Prodejce</th><th>Balení</th><th class="num">${u.label}</th>
          <th class="num">Za 7 dní</th><th class="num">Za 30 dní</th><th>Doprava</th></tr></thead>
        <tbody></tbody></table></div>`;
    const tbody = sec.querySelector("tbody");
    const delta = (cur, ref) => {
      if (!ref) return "–";
      const d = cur[unit] - ref[unit];
      if (Math.abs(d) < 10 ** -u.digits / 2) return "0";
      return `${d > 0 ? "▲ +" : "▼ "}${fmt(d, u.digits)}`;
    };
    latest.forEach((l, i) => {
      const s = DATA.sources[l.id];
      const st = DATA.status?.[l.id];
      const stale = l.cur.date !== lastDate || (st && !st.ok)
        ? `<div class="stale">naposledy ${fmtDate(l.cur.date)}</div>` : "";
      const tr = document.createElement("tr");
      if (i === 0) tr.className = "cheapest";
      tr.innerHTML = `
        <td><span class="swatch" style="background:${color[l.id]}"></span><a href="${s.url}" rel="noopener">${s.shop}</a>${stale}</td>
        <td>${l.cur.pack}</td>
        <td class="num"><strong>${fmt(l.cur[unit], u.digits)}</strong></td>
        <td class="num">${delta(l.cur, l.w)}</td>
        <td class="num">${delta(l.cur, l.m)}</td>
        <td>${l.cur.delivery_included ? "<strong>v ceně</strong>" : (s.delivery || "")}</td>`;
      tbody.appendChild(tr);
    });
    root.appendChild(sec);

    const canvas = sec.querySelector("canvas");
    if (charts[pid]) charts[pid].destroy();
    if (typeof Chart === "undefined") continue;
    charts[pid] = new Chart(canvas, {
      type: "line",
      data: {
        labels: dates.map(fmtDate),
        datasets: srcIds.filter((id) => rows.some((r) => r.source_id === id)).map((id) => {
          const byDate = Object.fromEntries(rows.filter((r) => r.source_id === id).map((r) => [r.date, r[unit]]));
          return {
            label: label(id),
            data: dates.map((d) => byDate[d] ?? null),
            borderColor: color[id],
            backgroundColor: color[id],
            borderWidth: 2,
            pointRadius: dates.length > 30 ? 0 : 4,
            pointHoverRadius: 6,
            pointBorderColor: cssVar("--surface-1"),
            pointBorderWidth: 2,
            spanGaps: true,
            tension: 0,
          };
        }),
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom", labels: { color: cssVar("--text-secondary"), boxWidth: 10, boxHeight: 10 } },
          tooltip: {
            itemSort: (a, b) => a.parsed.y - b.parsed.y,
            callbacks: { label: (c) => ` ${c.dataset.label}: ${fmt(c.parsed.y, u.digits)} ${u.label}` },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: cssVar("--text-muted") } },
          y: {
            grid: { color: cssVar("--grid") },
            ticks: { color: cssVar("--text-muted"), callback: (v) => fmt(v, u.digits) },
            title: { display: true, text: u.label, color: cssVar("--text-muted") },
          },
        },
      },
    });
  }
}

document.querySelectorAll(".controls button").forEach((b) =>
  b.addEventListener("click", () => {
    unit = b.dataset.unit;
    document.querySelectorAll(".controls button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    render();
  })
);

fetch("data/prices.json", { cache: "no-cache" })
  .then((r) => r.json())
  .then((d) => {
    DATA = d;
    document.getElementById("updated").textContent = `Aktualizováno ${new Date(d.updated).toLocaleString("cs-CZ")}.`;
    render();
  })
  .catch((e) => {
    document.getElementById("products").textContent = "Nepodařilo se načíst data: " + e;
  });
