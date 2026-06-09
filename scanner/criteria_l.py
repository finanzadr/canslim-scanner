"""
criteria_l.py — Leader or Laggard (L)
=======================================
Calcula la fuerza relativa vs S&P500 y verifica que el sector también esté fuerte.

Sub-criterios:
  L1 — RS vs SPX >= percentil 80 del universo escaneado
  L2 — Línea RS en tendencia alcista (últimas 8 semanas)
  L3 — Sector ETF también en Stage 2 (sobre MA30 semanal)
"""

import logging
import pandas as pd
import numpy as np
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.criteria_l")


@dataclass
class CriteriaLResult:
    passed:       bool  = False
    score:        int   = 0
    max_score:    int   = 3
    details:      dict  = field(default_factory=dict)
    note:         str   = ""

    rs_value:     float = 0.0    # rendimiento relativo vs SPX (12 meses)
    rs_percentile: int  = 0      # percentil estimado en el universo
    rs_trending:  bool  = False
    sector_strong: bool = False


def evaluate(price_data, spx_data, sector_data, rs_universe, cfg) -> CriteriaLResult:
    """
    Args:
        price_data:   PriceData de la acción
        spx_data:     DataFrame diario del SPX (de MarketData.spx)
        sector_data:  DataFrame semanal del ETF del sector (puede ser None)
        rs_universe:  list[float] de RS values de todas las acciones escaneadas
                      (para calcular percentil — puede ser vacía en primera pasada)
        cfg:          Config completo
    """
    res  = CriteriaLResult()
    lcfg = cfg.l

    if price_data.error or price_data.daily is None:
        res.note = f"Sin datos: {price_data.error}"
        return res

    checks = {}

    # ── L1 — RS vs SPX (rendimiento relativo 12 meses) ───────────────────
    rs_value, rs_pct = _calc_rs(
        price_data.daily,
        spx_data,
        period_days=lcfg.rs_period_days,
        universe_rs=rs_universe,
        min_percentile=lcfg.rs_percentile_min
    )

    c1 = rs_pct >= lcfg.rs_percentile_min
    checks["L1_rs_vs_spx"] = {
        "passed": c1,
        "value":  rs_pct,
        "target": lcfg.rs_percentile_min,
        "note":   f"RS {rs_value:+.1f}% vs SPX · percentil ~{rs_pct}"
    }
    res.rs_value      = round(rs_value, 2)
    res.rs_percentile = rs_pct

    # ── L2 — Línea RS en tendencia alcista ────────────────────────────────
    rs_trending = _rs_trending_up(
        price_data.daily,
        spx_data,
        weeks=lcfg.rs_trend_weeks
    )
    c2 = rs_trending
    checks["L2_rs_tendencia_alcista"] = {
        "passed": c2,
        "note":   f"RS {'subiendo' if c2 else 'bajando'} en últimas {lcfg.rs_trend_weeks} semanas"
    }
    res.rs_trending = c2

    # ── L3 — Sector en Stage 2 ────────────────────────────────────────────
    if lcfg.require_sector_stage2 and sector_data is not None and len(sector_data) >= 35:
        sector_close = sector_data["Close"]
        ma30_sector  = sector_close.rolling(30).mean()
        last_sc      = float(sector_close.iloc[-1])
        last_ma30    = float(ma30_sector.iloc[-1])
        prev_ma30    = float(ma30_sector.iloc[-5]) if len(ma30_sector) > 5 else last_ma30

        sector_ok = last_sc > last_ma30 and last_ma30 > prev_ma30
        c3 = sector_ok
        checks["L3_sector_stage2"] = {
            "passed": c3,
            "note":   (
                f"Sector ETF {last_sc:.2f} > MA30 {last_ma30:.2f} · "
                f"MA30 {'↑' if last_ma30 > prev_ma30 else '↓'}"
            )
        }
    else:
        c3 = not lcfg.require_sector_stage2
        checks["L3_sector_stage2"] = {
            "passed": c3,
            "note":   "Sin datos de sector ETF" if lcfg.require_sector_stage2
                      else "No requerido"
        }
    res.sector_strong = c3

    # ── Score ─────────────────────────────────────────────────────────────
    score      = sum([c1, c2, c3])
    res.passed  = score >= 2
    res.score   = score
    res.details = checks
    res.note = (
        f"L: {score}/3 — "
        f"RS {rs_value:+.1f}% · percentil ~{rs_pct} · "
        f"{'Sector ✓' if c3 else 'Sector ✗'}"
    )
    return res


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _calc_rs(daily: pd.DataFrame, spx: pd.DataFrame,
             period_days: int, universe_rs: list,
             min_percentile: int) -> tuple[float, int]:
    """
    Calcula rendimiento relativo de la acción vs SPX en period_days.
    Retorna (rs_value_pct, percentile_estimate).
    """
    if spx is None or len(daily) < period_days or len(spx) < period_days:
        return 0.0, 0

    try:
        stock_ret = (float(daily["Close"].iloc[-1]) /
                     float(daily["Close"].iloc[-period_days]) - 1) * 100
        spx_ret   = (float(spx["Close"].iloc[-1]) /
                     float(spx["Close"].iloc[-period_days]) - 1) * 100
        rs_val    = stock_ret - spx_ret

        # Percentil: si tenemos el universo, calculamos exacto
        if universe_rs:
            below = sum(1 for x in universe_rs if x <= rs_val)
            pct   = int(below / len(universe_rs) * 100)
        else:
            # Estimación simple basada en el valor absoluto
            # RS > +20% → percentil ~90, > +10% → ~80, > 0% → ~60
            if rs_val >= 30:
                pct = 95
            elif rs_val >= 20:
                pct = 88
            elif rs_val >= 10:
                pct = 80
            elif rs_val >= 0:
                pct = 65
            elif rs_val >= -10:
                pct = 45
            else:
                pct = 25

        return round(rs_val, 2), pct

    except (IndexError, ZeroDivisionError, TypeError) as exc:
        logger.debug(f"_calc_rs: {exc}")
        return 0.0, 0


def _rs_trending_up(daily: pd.DataFrame, spx: pd.DataFrame,
                    weeks: int) -> bool:
    """
    La línea RS (precio/SPX normalizado) está subiendo en las últimas N semanas.
    """
    lookback = weeks * 5
    if spx is None or len(daily) < lookback + 5 or len(spx) < lookback + 5:
        return False

    try:
        # Alinear por fecha
        stock = daily["Close"].rename("stock")
        bench = spx["Close"].rename("bench")
        merged = pd.merge_asof(
            stock.reset_index(), bench.reset_index(),
            on="Date", direction="nearest"
        ).set_index("Date")

        rs_line = merged["stock"] / merged["bench"]
        if len(rs_line) < lookback + 2:
            return False

        rs_now  = float(rs_line.iloc[-1])
        rs_then = float(rs_line.iloc[-(lookback + 1)])
        return rs_now > rs_then

    except Exception as exc:
        logger.debug(f"_rs_trending_up: {exc}")
        return False
