"""
criteria_c.py — Current quarterly earnings (C)
===============================================
Evalúa el crecimiento de EPS y ventas del trimestre más reciente.

Sub-criterios:
  C1 — EPS trimestral YoY >= 25%
  C2 — Ventas trimestrales YoY >= 25%
  C3 — Aceleración del EPS (último > penúltimo)
  C4 — Earnings beat (EPS actual > estimado analistas)
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.criteria_c")


@dataclass
class CriteriaCResult:
    passed:    bool  = False
    score:     int   = 0
    max_score: int   = 4
    details:   dict  = field(default_factory=dict)
    note:      str   = ""

    # Valores clave para la app web
    eps_growth:     float = 0.0
    revenue_growth: float = 0.0
    accelerating:   bool  = False
    beat_estimate:  bool  = False


def evaluate(fund_data, cfg) -> CriteriaCResult:
    """
    Evalúa el criterio C sobre los datos fundamentales.

    Args:
        fund_data: FundamentalData con quarterly_eps_yoy, quarterly_revenue_yoy
        cfg:       Config completo (usa cfg.c)

    Returns:
        CriteriaCResult con score 0–4
    """
    res  = CriteriaCResult()
    ccfg = cfg.c

    if fund_data.error:
        res.note = f"Sin datos: {fund_data.error}"
        return res

    checks = {}

    # ── C1 — EPS trimestral YoY ───────────────────────────────────────────
    if fund_data.quarterly_eps_yoy:
        eps_g = fund_data.quarterly_eps_yoy[0]
        c1    = eps_g >= ccfg.eps_growth_min
        checks["C1_eps_trimestral_yoy"] = {
            "passed": c1,
            "value":  round(eps_g * 100, 1),
            "target": round(ccfg.eps_growth_min * 100, 1),
            "note":   f"EPS YoY {eps_g*100:+.1f}% (mín {ccfg.eps_growth_min*100:.0f}%)"
        }
        res.eps_growth = eps_g
    else:
        c1 = False
        checks["C1_eps_trimestral_yoy"] = {
            "passed": False, "note": "Sin datos de EPS trimestral"
        }

    # ── C2 — Ventas trimestrales YoY ──────────────────────────────────────
    if fund_data.quarterly_revenue_yoy:
        rev_g = fund_data.quarterly_revenue_yoy[0]
        c2    = rev_g >= ccfg.revenue_growth_min
        checks["C2_ventas_trimestrales_yoy"] = {
            "passed": c2,
            "value":  round(rev_g * 100, 1),
            "target": round(ccfg.revenue_growth_min * 100, 1),
            "note":   f"Ventas YoY {rev_g*100:+.1f}% (mín {ccfg.revenue_growth_min*100:.0f}%)"
        }
        res.revenue_growth = rev_g
    else:
        c2 = False
        checks["C2_ventas_trimestrales_yoy"] = {
            "passed": False, "note": "Sin datos de ventas trimestral"
        }

    # ── C3 — Aceleración del EPS ──────────────────────────────────────────
    if ccfg.require_acceleration and len(fund_data.quarterly_eps_yoy) >= 2:
        curr_g = fund_data.quarterly_eps_yoy[0]
        prev_g = fund_data.quarterly_eps_yoy[1]
        c3     = curr_g > prev_g
        checks["C3_aceleracion_eps"] = {
            "passed": c3,
            "value":  round(curr_g * 100, 1),
            "target": round(prev_g * 100, 1),
            "note": (
                f"Trim actual {curr_g*100:+.1f}% > "
                f"trim anterior {prev_g*100:+.1f}%"
                if c3 else
                f"Sin aceleración: {curr_g*100:+.1f}% <= {prev_g*100:+.1f}%"
            )
        }
        res.accelerating = c3
    elif not ccfg.require_acceleration:
        c3 = True
        checks["C3_aceleracion_eps"] = {"passed": True, "note": "No requerida"}
    else:
        c3 = False
        checks["C3_aceleracion_eps"] = {
            "passed": False, "note": "Datos insuficientes para calcular aceleración"
        }

    # ── C4 — Earnings beat ────────────────────────────────────────────────
    if (ccfg.require_beat
            and fund_data.quarterly_eps
            and fund_data.quarterly_eps_estimate):
        actual    = fund_data.quarterly_eps[0]
        estimated = fund_data.quarterly_eps_estimate[0]
        if estimated and estimated != 0:
            beat_pct = (actual - estimated) / abs(estimated)
            c4 = beat_pct >= ccfg.beat_margin_min
            checks["C4_earnings_beat"] = {
                "passed": c4,
                "value":  round(beat_pct * 100, 1),
                "target": round(ccfg.beat_margin_min * 100, 1),
                "note":   f"Beat {beat_pct*100:+.1f}% (actual {actual:.2f} vs est {estimated:.2f})"
            }
            res.beat_estimate = c4
        else:
            # Sin estimado disponible — no penalizar
            c4 = True
            checks["C4_earnings_beat"] = {
                "passed": True, "note": "Sin estimado disponible (no penalizado)"
            }
    else:
        c4 = not ccfg.require_beat   # si no se requiere, pasa automáticamente
        checks["C4_earnings_beat"] = {
            "passed": c4,
            "note":   "No requerido" if not ccfg.require_beat else "Sin datos de estimado"
        }

    # ── Score final ───────────────────────────────────────────────────────
    passed_list = [c1, c2, c3, c4]
    score       = sum(passed_list)

    # C1 (EPS) es el criterio más importante — si falla con margen grande, penalizar
    if fund_data.quarterly_eps_yoy:
        eps_g = fund_data.quarterly_eps_yoy[0]
        if eps_g < 0:   # EPS negativo = descalificación directa de C
            score = 0
            checks["C1_eps_trimestral_yoy"]["note"] += " ⚠ EPS negativo"

    res.passed  = score >= 3   # al menos 3 de 4 sub-criterios
    res.score   = score
    res.details = checks
    res.note = (
        f"C: {score}/4 — EPS {res.eps_growth*100:+.1f}% · "
        f"Ventas {res.revenue_growth*100:+.1f}% · "
        f"{'Acelerando ✓' if res.accelerating else 'Sin aceleración'}"
    )

    return res
