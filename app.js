// app.js — CANSLIM Scanner Dashboard v2
// Muestra pivot, stop, target 3R y badge accionable

const DATA_URL = "data/results_latest.json"

let allResults = [];
let sortKey    = "score";
let sortDir    = -1;
let activeRow  = null;

// ── Cargar datos ──────────────────────────────────────────────────────────────

async function loadData() {
  document.getElementById("results-body").innerHTML =
    '<tr><td colspan="13" class="loading">Cargando datos del scanner...</td></tr>';
  try {
    const res  = await fetch(DATA_URL + "?t=" + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    document.getElementById("results-body").innerHTML =
      `<tr><td colspan="13" class="loading" style="color:var(--red)">
        Error cargando datos: ${err.message}<br>
        <small style="color:var(--muted)">El scanner corre automáticamente cada día a las 3:30pm ET.</small>
      </td></tr>`;
  }
}

// ── Renderizar dashboard ──────────────────────────────────────────────────────

function renderDashboard(data) {
  const date = data.date || data.generated_at?.split("T")[0] || "—";
  document.getElementById("scan-date").textContent = "Actualizado: " + date;
  document.getElementById("footer-date").textContent = "Scan: " + date;

  const badge = document.getElementById("market-badge");
  if (data.market_blocked) {
    badge.textContent = "⚠ Mercado bajista";
    badge.className   = "market-badge bajista";
    document.getElementById("market-blocked").style.display = "flex";
    document.getElementById("blocked-note").textContent = data.market_note || "";
    document.getElementById("results-body").innerHTML =
      '<tr><td colspan="13" class="loading">Scanner pausado — mercado no alcista</td></tr>';
    return;
  }
  badge.textContent = "✓ Mercado alcista";
  badge.className   = "market-badge alcista";
  document.getElementById("market-blocked").style.display = "none";

  allResults = data.results || [];

  const elite      = allResults.filter(r => r.grade === "elite").length;
  const strong     = allResults.filter(r => r.grade === "strong").length;
  const actionable = allResults.filter(r => r.details?.entry?.actionable).length;
  document.getElementById("m-passing").textContent  = allResults.length;
  document.getElementById("m-elite").textContent    = elite;
  document.getElementById("m-strong").textContent   = strong;
  document.getElementById("m-total").textContent    = data.total_scanned || "—";

  // Actualizar métrica de accionables si existe el elemento
  const mAct = document.getElementById("m-actionable");
  if (mAct) mAct.textContent = actionable;

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
  const query      = document.getElementById("search").value.toLowerCase();
  const grade      = document.getElementById("filter-grade").value;
  const sector     = document.getElementById("filter-sector").value;
  const actionOnly = document.getElementById("filter-actionable")?.checked;

  let rows = allResults.filter(r => {
    if (query      && !r.ticker.toLowerCase().includes(query)
                   && !(r.name||"").toLowerCase().includes(query)) return false;
    if (grade      && r.grade !== grade)   return false;
    if (sector     && r.sector !== sector) return false;
    if (actionOnly && !r.details?.entry?.actionable) return false;
    return true;
  });

  rows.sort((a, b) => {
    let av, bv;
    switch (sortKey) {
      case "ticker": av = a.ticker; bv = b.ticker; break;
      case "eps":    av = a.metrics?.eps_growth || 0; bv = b.metrics?.eps_growth || 0; break;
      case "roe":    av = a.metrics?.roe        || 0; bv = b.metrics?.roe        || 0; break;
      case "rs":     av = a.metrics?.rs_value   || 0; bv = b.metrics?.rs_value   || 0; break;
      case "pivot":  av = a.details?.entry?.pivot || 0; bv = b.details?.entry?.pivot || 0; break;
      default:       av = a.score || 0; bv = b.score || 0;
    }
    if (av < bv) return sortDir;
    if (av > bv) return -sortDir;
    return 0;
  });

  const tbody = document.getElementById("results-body");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="13" class="loading">Sin resultados con los filtros actuales</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map((r, i) => rowHtml(r, i + 1)).join("");

  tbody.querySelectorAll("tr[data-ticker]").forEach(tr => {
    tr.addEventListener("click", e => {
      if (e.target.tagName === "A") return;
      const result = allResults.find(r => r.ticker === tr.dataset.ticker);
      if (result) showDetail(result, tr);
    });
  });
}

function rowHtml(r, rank) {
  const m      = r.metrics || {};
  const entry  = r.details?.entry || {};
  const score  = r.score   || 0;
  const maxS   = r.max_score || 32;
  const pct    = Math.round(score / maxS * 100);

  const barColor = score >= 30 ? "#bc8cff"
                 : score >= 27 ? "#3fb950"
                 : score >= 22 ? "#58a6ff" : "#8b949e";

  const gradeBadge = {
    elite:  '<span class="grade-badge grade-elite">★★ Élite</span>',
    strong: '<span class="grade-badge grade-strong">★ Fuerte</span>',
    valid:  '<span class="grade-badge grade-valid">✓ Válido</span>',
    weak:   '<span class="grade-badge grade-weak">Débil</span>',
  }[r.grade] || "";

  const stage = r.weinstein_stage || 0;
  const stageBadge = stage === 2
    ? '<span class="stage-badge stage-2">S2</span>'
    : `<span class="stage-badge stage-other">S${stage}</span>`;

  // Entry params
  const pivot      = entry.pivot      || 0;
  const stop       = entry.stop       || 0;
  const target3r   = entry.target_3r  || 0;
  const actionable = entry.actionable || false;
  const baseType   = entry.base_type  || "";
  const riskPct    = entry.risk_pct   || 8;

  // Badge accionable
  const actionBadge = pivot > 0
    ? actionable
      ? `<span class="action-badge action-yes" title="Precio dentro del 3% del pivot — comprar hoy">⚡ Ahora</span>`
      : `<span class="action-badge action-wait" title="Esperar al pivot">⏳ Esperar</span>`
    : `<span class="action-badge action-none">—</span>`;

  // Entry cell
  let entryCell = "—";
  if (pivot > 0) {
    const curr = entry.current_price || 0;
    const ext  = curr > 0 ? ((curr - pivot) / pivot * 100).toFixed(1) : null;
    entryCell = `
      <div style="font-size:12px;line-height:1.6">
        <div><span style="color:var(--muted);font-size:10px">PIVOT</span> <strong style="color:var(--text)">$${pivot}</strong></div>
        <div><span style="color:var(--muted);font-size:10px">STOP </span> <span style="color:var(--red)">$${stop}</span> <span style="font-size:10px;color:var(--muted)">-${riskPct}%</span></div>
        <div><span style="color:var(--muted);font-size:10px">T3R  </span> <span style="color:var(--green)">$${target3r}</span></div>
        ${baseType ? `<div style="font-size:10px;color:var(--muted)">${baseType}</div>` : ""}
      </div>`;
  }

  // Earnings warning
  const earn    = r.earnings || {};
  const earnDate = earn.next_date || "";
  const earnDays = earn.days_to  ?? -1;
  const earnWarn = earn.warning  || false;

  let earnBadge = "";
  if (earnDate) {
    if (earnWarn) {
      earnBadge = `<div style="margin-top:3px"><span style="font-size:10px;padding:1px 5px;border-radius:3px;background:rgba(210,153,34,.15);color:#d29922;border:1px solid rgba(210,153,34,.3)">⚠ Earnings ${earnDays}d</span></div>`;
    } else {
      earnBadge = `<div style="margin-top:3px;font-size:10px;color:var(--muted)">Earn: ${earnDate}</div>`;
    }
  }

  const fmtPct = v => `<span class="${v >= 25 ? "val-pos" : v < 0 ? "val-neg" : ""}">${v > 0 ? "+" : ""}${v.toFixed(1)}%</span>`;
  const fmtRs  = v => `<span class="${v >= 10 ? "val-pos" : v < 0 ? "val-neg" : "val-neutral"}">${v > 0 ? "+" : ""}${v.toFixed(1)}%</span>`;

  const eps  = m.eps_growth ?? 0;
  const roe  = m.roe        ?? 0;
  const rs   = m.rs_value   ?? 0;

  const tvUrl = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(r.ticker)}`;
  const cap  = r.market_cap >= 1e12 ? `$${(r.market_cap/1e12).toFixed(1)}T`
             : r.market_cap >= 1e9  ? `$${(r.market_cap/1e9).toFixed(1)}B` : "";

  return `<tr data-ticker="${r.ticker}">
    <td class="col-rank">${rank}</td>
    <td class="col-ticker">
      ${r.ticker}
      ${cap ? `<div style="font-size:10px;color:var(--muted)">${cap}</div>` : ""}
      ${earnBadge}
    </td>
    <td class="col-score">
      <div class="score-bar-wrap">
        <div class="score-bar"><div class="score-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
        <span class="score-num" style="color:${barColor}">${score}</span>
      </div>
    </td>
    <td class="col-grade">${gradeBadge}</td>
    <td class="col-stage">${stageBadge}</td>
    <td class="col-action-badge">${actionBadge}</td>
    <td class="col-entry">${entryCell}</td>
    <td class="col-eps">${fmtPct(eps)}</td>
    <td class="col-roe">${fmtPct(roe)}</td>
    <td class="col-rs">${fmtRs(rs)}</td>
    <td class="col-sector" style="font-size:12px;color:var(--muted)">${r.sector || "—"}</td>
    <td class="col-tv">
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

  const scores = r.scores || {};
  const maxes  = { weinstein:6, M:5, C:4, A:4, N:4, S:4, L:3, I:3 };
  const colors = { weinstein:"#d29922", M:"#3fb950", C:"#58a6ff",
                   A:"#58a6ff", N:"#3fb950", S:"#3fb950", L:"#d29922", I:"#d29922" };
  const labels = { weinstein:"W·S2", M:"M", C:"C", A:"A", N:"N", S:"S", L:"L", I:"I" };

  document.getElementById("d-scores").innerHTML = Object.entries(scores).map(([k, v]) => {
    const max   = maxes[k] || 5;
    const color = v === max ? colors[k] : v >= max * 0.6 ? colors[k] : "var(--muted)";
    return `<div class="ds-card">
      <div class="ds-letter">${labels[k] || k}</div>
      <div class="ds-score" style="color:${color}">${v}<span style="font-size:11px;color:var(--muted)">/${max}</span></div>
    </div>`;
  }).join("");

  // Entry setup destacado
  const entry = r.details?.entry || {};
  const earn  = r.earnings || {};
  let entryHtml = "";

  // Warning de earnings
  if (earn.next_date) {
    const warnStyle = earn.warning
      ? "background:rgba(210,153,34,.1);border:1px solid rgba(210,153,34,.3);color:#d29922"
      : "background:var(--surface);border:0.5px solid var(--border);color:var(--muted)";
    entryHtml += `<div style="font-size:12px;padding:6px 10px;border-radius:6px;margin-bottom:8px;${warnStyle}">
      ${earn.warning ? "⚠" : "📅"} Próximos earnings: <strong>${earn.next_date}</strong>
      ${earn.days_to >= 0 ? `· en ${earn.days_to} días` : ""}
      ${earn.warning ? " — <strong>Precaución: no entrar antes de reportar</strong>" : ""}
    </div>`;
  }
  if (entry.valid && entry.pivot) {
    const actionable = entry.actionable;
    const rr = entry.rr_ratio || 3;
    entryHtml = `
    <div class="dc-group" style="background:${actionable ? "rgba(63,185,80,.08)" : "rgba(88,166,255,.05)"};border-radius:6px;padding:8px 10px;margin-bottom:8px">
      <div class="dc-group-title" style="color:${actionable ? "var(--green)" : "var(--blue)"}">
        ${actionable ? "⚡ SETUP ACCIONABLE AHORA" : "⏳ Setup — esperando pivot"}
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px">
        <div style="text-align:center">
          <div style="font-size:10px;color:var(--muted)">ENTRADA</div>
          <div style="font-size:16px;font-weight:600;color:var(--text)">$${entry.pivot}</div>
          <div style="font-size:10px;color:var(--muted)">${entry.base_type || ""}</div>
        </div>
        <div style="text-align:center">
          <div style="font-size:10px;color:var(--muted)">STOP</div>
          <div style="font-size:16px;font-weight:600;color:var(--red)">$${entry.stop}</div>
          <div style="font-size:10px;color:var(--muted)">-${entry.risk_pct}%</div>
        </div>
        <div style="text-align:center">
          <div style="font-size:10px;color:var(--muted)">TARGET 3R</div>
          <div style="font-size:16px;font-weight:600;color:var(--green)">$${entry.target_3r}</div>
          <div style="font-size:10px;color:var(--muted)">R:R 1:${rr}</div>
        </div>
      </div>
      <div style="display:flex;gap:12px;margin-top:8px;font-size:12px;color:var(--muted)">
        <span>Base ${entry.base_weeks}w · ${entry.base_tightness}% rango</span>
        <span>T1R $${entry.target_1r}</span>
        <span>T2R $${entry.target_2r}</span>
      </div>
    </div>`;
  }

  // Criterios CANSLIM
  const details    = r.details || {};
  const groupOrder = ["weinstein", "M", "C", "A", "N", "S", "L", "I"];
  const groupNames = {
    weinstein:"Weinstein Stage 2", M:"M — Mercado", C:"C — EPS trimestral",
    A:"A — EPS anual", N:"N — Ruptura", S:"S — Supply & demand",
    L:"L — Relative Strength", I:"I — Institucional",
  };

  let html = entryHtml;
  for (const group of groupOrder) {
    const gd = details[group];
    if (!gd || typeof gd !== "object") continue;
    html += `<div class="dc-group"><div class="dc-group-title">${groupNames[group] || group}</div>`;
    for (const [key, check] of Object.entries(gd)) {
      const icon = check.passed
        ? '<span class="dc-icon dc-pass">✓</span>'
        : '<span class="dc-icon dc-fail">✗</span>';
      html += `<div class="dc-row">${icon}
        <span class="dc-name">${key.replace(/_/g," ").replace(/^[A-Z]\d\s/,"")}</span>
        <span class="dc-note">${check.note || ""}</span>
      </div>`;
    }
    html += "</div>";
  }

  document.getElementById("d-criteria").innerHTML = html;
  const panel = document.getElementById("detail-panel");
  panel.style.display = "block";
  panel.scrollIntoView({ behavior:"smooth", block:"nearest" });
}

function closeDetail() {
  document.getElementById("detail-panel").style.display = "none";
  if (activeRow) { activeRow.style.background = ""; activeRow = null; }
}

// ── Sorting & filtros ─────────────────────────────────────────────────────────

document.querySelectorAll("th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (sortKey === key) sortDir *= -1;
    else { sortKey = key; sortDir = -1; }
    renderTable();
  });
});

document.getElementById("search").addEventListener("input", renderTable);
document.getElementById("filter-grade").addEventListener("change", renderTable);
document.getElementById("filter-sector").addEventListener("change", renderTable);
document.getElementById("filter-actionable")?.addEventListener("change", renderTable);

loadData();
