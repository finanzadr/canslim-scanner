"""
criteria_i.py — Institutional Sponsorship (I)
===============================================
Verifica que los institucionales estén acumulando, no saliendo.

Sub-criterios:
  I1 — % institucional en rango ideal (30–80%)
  I2 — Tendencia institucional creciente
  I3 — Sin concentración excesiva en un solo fondo
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.criteria_i")


@dataclass
class CriteriaIResult:
    passed:       bool  = False
    score:        int   = 0
    max_score:    int   = 3
    details:      dict  = field(default_factory=dict)
    note:         str   = ""

    inst_pct:       float = 0.0
    inst_trending:  bool  = False
    concentration_ok: bool = True


def evaluate(fund_data, cfg) -> CriteriaIResult:
    res  = CriteriaIResult()
    icfg = cfg.i

    checks = {}

    # ── I1 — % institucional en rango ideal ───────────────────────────────
    inst_pct = fund_data.institutional_pct if fund_data else 0.0
    res.inst_pct = inst_pct

    if inst_pct > 0:
        in_range = icfg.inst_pct_min <= inst_pct <= icfg.inst_pct_max
        in_ideal = icfg.inst_pct_ideal_low <= inst_pct <= icfg.inst_pct_ideal_high
        c1 = in_range

        if inst_pct < icfg.inst_pct_min:
            note_i1 = f"{inst_pct*100:.1f}% — muy bajo (mín {icfg.inst_pct_min*100:.0f}%)"
        elif inst_pct > icfg.inst_pct_max:
            note_i1 = f"{inst_pct*100:.1f}% — sobre-tenida (máx {icfg.inst_pct_max*100:.0f}%)"
        else:
            note_i1 = f"{inst_pct*100:.1f}% {'★ zona ideal' if in_ideal else '· rango aceptable'}"
    else:
        c1      = False
        note_i1 = "Sin datos institucionales"

    checks["I1_pct_institucional"] = {
        "passed": c1,
        "value":  round(inst_pct * 100, 1),
        "target": f"{icfg.inst_pct_min*100:.0f}–{icfg.inst_pct_max*100:.0f}%",
        "note":   note_i1
    }

    # ── I2 — Tendencia creciente ──────────────────────────────────────────
    inst_prev = fund_data.institutional_pct_prev if fund_data else 0.0

    if inst_pct > 0 and inst_prev > 0:
        trending_up = inst_pct > inst_prev
        change      = inst_pct - inst_prev
        c2 = trending_up
        checks["I2_tendencia_institucional"] = {
            "passed": c2,
            "note":   f"{'↑' if trending_up else '↓'} {change*100:+.1f}% vs trimestre anterior"
        }
    else:
        # Sin dato previo — no penalizar si el % actual es bueno
        c2 = c1
        checks["I2_tendencia_institucional"] = {
            "passed": c2,
            "note":   "Sin dato trimestre anterior — estimado por % actual"
        }
    res.inst_trending = c2

    # ── I3 — Sin concentración excesiva ───────────────────────────────────
    # yfinance no da desglose por fondo — asumimos OK si % total <= 80%
    # Con FMP se puede calcular exacto
    c3 = inst_pct <= icfg.inst_pct_max
    checks["I3_sin_concentracion"] = {
        "passed": c3,
        "note": (
            "Concentración aceptable"
            if c3 else
            f"Posible sobre-concentración ({inst_pct*100:.1f}% > {icfg.inst_pct_max*100:.0f}%)"
        )
    }
    res.concentration_ok = c3

    # ── Score ─────────────────────────────────────────────────────────────
    score      = sum([c1, c2, c3])
    res.passed  = score >= 2
    res.score   = score
    res.details = checks
    res.note = (
        f"I: {score}/3 — "
        f"Inst {inst_pct*100:.1f}% · "
        f"{'Tendencia ↑' if c2 else 'Tendencia ↓'}"
    )
    return res
