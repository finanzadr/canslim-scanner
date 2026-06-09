// app.js — CANSLIM Scanner Dashboard
// Lee results_latest.json y renderiza la tabla con filtros y detalle

const DATA_URL = "../data/results_latest.json";

let allResults  = [];
let sortKey     = "score";
let sortDir     = -1;   // -1 = desc, 1 = asc
let activeRow   = null;

// ── Cargar datos ──────────────────────────────────────────────────────────────

async function loadData() {
  document.getElementById("results-body").innerHTML =
    '<tr><td colspan="11" class="loading">Cargando datos del scanner...</td></tr>';

  try {
    const res  = await fetch(DATA_URL + "?t=" + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    document.getElementById("results-body").innerHTML =
      `<tr><td colspan="11" class="loading" style="color:var(--red)">
        Error cargando datos: ${err.message}<br>
        <small style="color:var(--muted)">
          El scanner aún no ha corrido o no hay conexión.
          El archivo se genera automáticamente cada día a las 5:15pm ET.
        </small>
      </td></tr>`;
  }
}

// ── Renderizar dashboard ──────────────────────────────────────────────────────

function renderDashboard(data) {
  // Fecha
  const date = data.date || data.generated_at?.split("T")[0] || "—";
  document.getElementById("scan-date").textContent = "Actualizado: " + date;
  document.getElementById("footer-date").textContent = "Scan: " + date;

  // Mercado
  const badge = document.getElementById("market-badge");
  if (data.market_blocked) {
    badge.textContent = "⚠ Mercado bajista";
    badge.className   = "market-badge bajista";
    document.getElementById("market-blocked").style.display = "flex";
    document.getElementById("blocked-note").textContent = data.market_note || "";
    document.getElementById("results-body").innerHTML =
      '<tr><td colspan="11" class="loading">Scanner pausado — mercado no alcista</td></tr>';
    return;
  } else {
    badge.textContent = "✓ Mercado alcista";
    badge.className   = "market-badge alcista";
    document.getElementById("market-blocked").style.display = "none";
  }

  allResults = data.results || [];

  // Métricas
  const elite  = allResults.filter(r => r.grade === "elite").length;
  const strong = allResults.filter(r => r.grade === "strong").length;
  document.getElementById("m-passing").textContent = allResults.length;
  document.getElementById("m-elite").textContent   = elite;
  document.getElementById("m-strong").textContent  = strong;
  document.getElementById("m-total").textContent   = data.total_scanned || "—";

  // Sectores para filtro
  const sectors = [...new Set(allResults.map(r => r.sector).filter(Boolean))].sort();
  const selSector = document.getElementById("filter-sector");
  selSector.innerHTML = '<option value="">Todos los sectores</option>';
  sectors.forEach(s => {
    const o = document.createElement("option");
    o.value = s; o.textContent = s;
    selSector.appendChild(o);
  });

  renderTable();
}

// ── Renderizar tabla ──────────────────────────────────────────────────────────

function renderTable() {
  const query  = document.getElementById("search").value.toLowerCase();
  const grade  = document.getElementById("filter-grade").value;
  const sector = document.getElementById("filter-sector").value;

  let rows = allResults.filter(r => {
    if (query  && !r.ticker.toLowerCase().includes(query)
                && !r.name.toLowerCase().includes(query))  return false;
    if (grade  && r.grade !== grade)                        return false;
    if (sector && r.sector !== sector)                      return false;
    return true;
  });

  // Ordenar
  rows.sort((a, b) => {
    let av, bv;
    switch (sortKey) {
      case "ticker": av = a.ticker; bv = b.ticker; break;
      case "eps":    av = a.metrics?.eps_growth    || 0; bv = b.metrics?.eps_growth    || 0; break;
      case "roe":    av = a.metrics?.roe           || 0; bv = b.metrics?.roe           || 0; break;
      case "rs":     av = a.metrics?.rs_value      || 0; bv = b.metrics?.rs_value      || 0; break;
      default:       av = a.score || 0;                  bv = b.score || 0;
    }
    if (av < bv) return sortDir;
    if (av > bv) return -sortDir;
    return 0;
  });

  const tbody = document.getElementById("results-body");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="11" class="loading">Sin resultados con los filtros actuales</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map((r, i) => rowHtml(r, i + 1)).join("");

  // Click en fila
  tbody.querySelectorAll("tr[data-ticker]").forEach(tr => {
    tr.addEventListener("click", e => {
      if (e.target.tagName === "A") return;
      const ticker = tr.dataset.ticker;
      const result = allResults.find(r => r.ticker === ticker);
      if (result) showDetail(result, tr);
    });
  });
}

function rowHtml(r, rank) {
  const m        = r.metrics || {};
  const scores   = r.scores  || {};
  const score    = r.score   || 0;
  const maxScore = r.max_score || 32;
  const pct      = Math.round(score / maxScore * 100);

  const barColor = score >= 30 ? "#bc8cff"
                 : score >= 27 ? "#3fb950"
                 : score >= 22 ? "#58a6ff"
                 : "#8b949e";

  const gradeBadge = {
    elite:  '<span class="grade-badge grade-elite">★★ Élite</span>',
    strong: '<span class="grade-badge grade-strong">★ Fuerte</span>',
    valid:  '<span class="grade-badge grade-valid">✓ Válido</span>',
    weak:   '<span class="grade-badge grade-weak">Débil</span>',
  }[r.grade] || "";

  const stage    = r.weinstein_stage || 0;
  const stageBadge = stage === 2
    ? '<span class="stage-badge stage-2">S2</span>'
    : `<span class="stage-badge stage-other">S${stage}</span>`;

  const eps   = m.eps_growth   ?? 0;
  const roe   = m.roe          ?? 0;
  const rs    = m.rs_value     ?? 0;
  const vol   = m.vol_ratio    ?? 0;

  const fmtPct  = v => `<span class="${v >= 25 ? "val-pos" : v < 0 ? "val-neg" : ""}">${v > 0 ? "+" : ""}${v.toFixed(1)}%</span>`;
  const fmtRs   = v => `<span class="${v >= 10 ? "val-pos" : v < 0 ? "val-neg" : "val-neutral"}">${v > 0 ? "+" : ""}${v.toFixed(1)}%</span>`;
  const fmtVol  = v => v > 0 ? `<span class="${v >= 1.4 ? "val-pos" : "val-neutral"}">${v.toFixed(1)}×</span>` : "—";

  const tvUrl   = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(r.ticker)}`;
  const cap     = r.market_cap >= 1e12 ? `$${(r.market_cap/1e12).toFixed(1)}T`
                : r.market_cap >= 1e9  ? `$${(r.market_cap/1e9).toFixed(1)}B` : "";

  return `<tr data-ticker="${r.ticker}">
    <td class="col-rank">${rank}</td>
    <td class="col-ticker">
      ${r.ticker}
      ${cap ? `<div style="font-size:10px;color:var(--muted);font-weight:400">${cap}</div>` : ""}
    </td>
    <td class="col-score">
      <div class="score-bar-wrap">
        <div class="score-bar"><div class="score-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
        <span class="score-num" style="color:${barColor}">${score}</span>
      </div>
    </td>
    <td class="col-grade">${gradeBadge}</td>
    <td class="col-stage">${stageBadge}</td>
    <td class="col-eps">${fmtPct(eps)}</td>
    <td class="col-roe">${fmtPct(roe)}</td>
    <td class="col-rs">${fmtRs(rs)}</td>
    <td class="col-vol">${fmtVol(vol)}</td>
    <td class="col-sector" style="font-size:12px;color:var(--muted)">${r.sector || "—"}</td>
    <td class="col-action">
      <a href="${tvUrl}" target="_blank" class="tv-link" title="Ver en TradingView">TV</a>
    </td>
  </tr>`;
}

// ── Panel de detalle ──────────────────────────────────────────────────────────

function showDetail(r, tr) {
  if (activeRow) activeRow.style.background = "";
  activeRow = tr;
  tr.style.background = "rgba(88,166,255,.08)";

  document.getElementById("d-ticker").textContent = r.ticker;
  document.getElementById("d-name").textContent   = r.name || "";

  // Mini scores por criterio
  const scores  = r.scores || {};
  const maxes   = { weinstein:6, M:5, C:4, A:4, N:4, S:4, L:3, I:3 };
  const colors  = { weinstein:"#d29922", M:"#3fb950", C:"#58a6ff",
                    A:"#58a6ff", N:"#3fb950", S:"#3fb950", L:"#d29922", I:"#d29922" };
  const labels  = { weinstein:"W·S2", M:"M", C:"C", A:"A", N:"N", S:"S", L:"L", I:"I" };

  document.getElementById("d-scores").innerHTML = Object.entries(scores).map(([k, v]) => {
    const max   = maxes[k] || 5;
    const pct   = Math.round(v / max * 100);
    const color = v === max ? colors[k] : v >= max * 0.6 ? colors[k] : "var(--muted)";
    return `<div class="ds-card">
      <div class="ds-letter">${labels[k] || k}</div>
      <div class="ds-score" style="color:${color}">${v}<span style="font-size:11px;color:var(--muted)">/${max}</span></div>
    </div>`;
  }).join("");

  // Criterios detallados
  const details = r.details || {};
  const groupOrder = ["weinstein", "M", "C", "A", "N", "S", "L", "I"];
  const groupNames = {
    weinstein: "Weinstein Stage 2",
    M: "M — Dirección del mercado",
    C: "C — EPS trimestral",
    A: "A — EPS anual",
    N: "N — Ruptura / nuevo máximo",
    S: "S — Supply & demand",
    L: "L — Relative Strength",
    I: "I — Institucional",
  };

  let html = "";
  for (const group of groupOrder) {
    const groupData = details[group];
    if (!groupData || typeof groupData !== "object") continue;
    html += `<div class="dc-group">
      <div class="dc-group-title">${groupNames[group] || group}</div>`;
    for (const [key, check] of Object.entries(groupData)) {
      const icon = check.passed
        ? '<span class="dc-icon dc-pass">✓</span>'
        : '<span class="dc-icon dc-fail">✗</span>';
      const cleanKey = key.replace(/_/g, " ").replace(/^[A-Z]\d\s/, "");
      html += `<div class="dc-row">
        ${icon}
        <span class="dc-name">${cleanKey}</span>
        <span class="dc-note">${check.note || ""}</span>
      </div>`;
    }
    html += "</div>";
  }

  document.getElementById("d-criteria").innerHTML = html;
  const panel = document.getElementById("detail-panel");
  panel.style.display = "block";
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function closeDetail() {
  document.getElementById("detail-panel").style.display = "none";
  if (activeRow) { activeRow.style.background = ""; activeRow = null; }
}

// ── Sorting ───────────────────────────────────────────────────────────────────

document.querySelectorAll("th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (sortKey === key) sortDir *= -1;
    else { sortKey = key; sortDir = -1; }
    renderTable();
  });
});

// ── Filtros en tiempo real ────────────────────────────────────────────────────

document.getElementById("search").addEventListener("input", renderTable);
document.getElementById("filter-grade").addEventListener("change", renderTable);
document.getElementById("filter-sector").addEventListener("change", renderTable);

// ── Arrancar ──────────────────────────────────────────────────────────────────

loadData();
