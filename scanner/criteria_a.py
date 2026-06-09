"""
criteria_a.py — Annual earnings growth (A)
==========================================
Confirma que el crecimiento es sostenido, no un trimestre aislado.

Sub-criterios:
  A1 — EPS anual >= 25% en 3 años consecutivos
  A2 — ROE >= 17%
  A3 — Margen neto estable o en alza
  A4 — Sin año con EPS negativo en el período
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.criteria_a")


@dataclass
class CriteriaAResult:
    passed:    bool  = False
    score:     int   = 0
    max_score: int   = 4
    details:   dict  = field(default_factory=dict)
    note:      str   = ""

    # Valores clave para la app web
    eps_annual_growths: list  = field(default_factory=list)
    roe_latest:         float = 0.0
    margin_latest:      float = 0.0
    has_negative_eps:   bool  = False


def evaluate(fund_data, cfg) -> CriteriaAResult:
    """
    Evalúa el criterio A sobre los datos fundamentales.

    Args:
        fund_data: FundamentalData con annual_eps, annual_roe, annual_net_margin
        cfg:       Config completo (usa cfg.a)

    Returns:
        CriteriaAResult con score 0–4
    """
    res  = CriteriaAResult()
    acfg = cfg.a

    if fund_data.error:
        res.note = f"Sin datos: {fund_data.error}"
        return res

    checks = {}

    # ── A1 — EPS anual N años consecutivos ────────────────────────────────
    years = acfg.years_required
    if len(fund_data.annual_eps) >= years + 1:
        growths = []
        all_positive = True

        for i in range(years):
            curr = fund_data.annual_eps[i]
            prev = fund_data.annual_eps[i + 1]

            if prev and prev != 0:
                g = (curr - prev) / abs(prev)
            else:
                g = 0.0
            growths.append(g)

            if curr < 0:
                all_positive = False

        min_g   = min(growths) if growths else 0.0
        all_met = all(g >= acfg.eps_annual_growth_min for g in growths)
        c1      = all_met and all_positive

        growths_str = "  ".join(f"{g*100:+.1f}%" for g in growths)
        checks["A1_eps_anual_consecutivo"] = {
            "passed": c1,
            "value":  round(min_g * 100, 1),
            "target": round(acfg.eps_annual_growth_min * 100, 1),
            "note":   f"Crec. {years} años: {growths_str}"
        }
        res.eps_annual_growths = [round(g * 100, 1) for g in growths]
        res.has_negative_eps   = not all_positive

    else:
        c1 = False
        checks["A1_eps_anual_consecutivo"] = {
            "passed": False,
            "note":   f"Datos insuficientes ({len(fund_data.annual_eps)} años, necesita {years+1})"
        }

    # ── A2 — ROE ──────────────────────────────────────────────────────────
    if fund_data.annual_roe:
        roe = fund_data.annual_roe[0]
        c2  = roe >= acfg.roe_min
        checks["A2_roe"] = {
            "passed": c2,
            "value":  round(roe * 100, 1),
            "target": round(acfg.roe_min * 100, 1),
            "note":   f"ROE {roe*100:.1f}% (mín {acfg.roe_min*100:.0f}%)"
        }
        res.roe_latest = roe
    else:
        c2 = False
        checks["A2_roe"] = {"passed": False, "note": "Sin datos de ROE"}

    # ── A3 — Margen neto ──────────────────────────────────────────────────
    if fund_data.annual_net_margin:
        margin = fund_data.annual_net_margin[0]
        c3     = margin >= acfg.net_margin_min

        # Verificar que no se esté comprimiendo (año actual >= año anterior)
        if acfg.net_margin_stable and len(fund_data.annual_net_margin) >= 2:
            prev_margin = fund_data.annual_net_margin[1]
            margin_ok   = margin >= prev_margin * 0.90   # permite caída < 10%
            c3 = c3 and margin_ok
            trend_note  = f" · tendencia {'OK' if margin_ok else 'comprimiendo'}"
        else:
            trend_note = ""

        checks["A3_margen_neto"] = {
            "passed": c3,
            "value":  round(margin * 100, 1),
            "target": round(acfg.net_margin_min * 100, 1),
            "note":   f"Margen {margin*100:.1f}% (mín {acfg.net_margin_min*100:.0f}%){trend_note}"
        }
        res.margin_latest = margin
    else:
        c3 = False
        checks["A3_margen_neto"] = {"passed": False, "note": "Sin datos de margen"}

    # ── A4 — Sin EPS negativo ─────────────────────────────────────────────
    if acfg.reject_any_negative_eps and fund_data.annual_eps:
        eps_to_check = fund_data.annual_eps[:years]
        has_neg      = any(e < 0 for e in eps_to_check)
        c4           = not has_neg
        checks["A4_sin_eps_negativo"] = {
            "passed": c4,
            "note": (
                "EPS negativo detectado en el período — descalificado"
                if has_neg else
                f"Sin EPS negativo en {years} años"
            )
        }
        res.has_negative_eps = has_neg
    else:
        c4 = True
        checks["A4_sin_eps_negativo"] = {
            "passed": True, "note": "No requerido"
        }

    # ── Score final ───────────────────────────────────────────────────────
    passed_list = [c1, c2, c3, c4]
    score       = sum(passed_list)

    # EPS negativo es descalificador absoluto — anula todo A
    if acfg.reject_any_negative_eps and res.has_negative_eps:
        score = 0

    res.passed  = score >= 3
    res.score   = score
    res.details = checks
    res.note = (
        f"A: {score}/4 — "
        f"ROE {res.roe_latest*100:.1f}% · "
        f"Margen {res.margin_latest*100:.1f}% · "
        f"{'EPS ✓' if c1 else 'EPS ✗'}"
    )

    return res
