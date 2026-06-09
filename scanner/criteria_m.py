"""
criteria_m.py — Dirección del mercado (M)
==========================================
Portero #2 — bloqueante de sesión completa.
Si el mercado no está alcista, el scanner devuelve 0 acciones.

Evalúa SPY (S&P500) y QQQ (Nasdaq):
  1. SPX sobre MA50 diario
  2. SPX sobre MA200 diario
  3. Nasdaq sobre MA50 diario
  4. Días de distribución <= umbral (últimas 25 sesiones)
  5. Follow-Through Day confirmado (opcional)
"""

import logging
import pandas as pd
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.criteria_m")


@dataclass
class MarketResult:
    passed:       bool  = False
    score:        int   = 0
    max_score:    int   = 5
    bullish:      bool  = False
    details:      dict  = field(default_factory=dict)
    note:         str   = ""

    # Para la app web
    spx_trend:    str   = ""   # "alcista" | "bajista" | "neutral"
    dist_days:    int   = 0
    ftd_active:   bool  = False


def evaluate(market_data, cfg) -> MarketResult:
    """
    Evalúa la dirección del mercado.

    Args:
        market_data: MarketData con .spx y .nasdaq
        cfg:         Config completo (usa cfg.market)

    Returns:
        MarketResult con passed=True si el mercado está alcista
    """
    res  = MarketResult()
    mcfg = cfg.market

    if market_data.error or market_data.spx is None:
        res.note = f"Sin datos de mercado: {market_data.error}"
        return res

    spx    = market_data.spx
    nasdaq = market_data.nasdaq

    checks = {}

    # ── 1. SPX sobre MA50 ─────────────────────────────────────────────────
    spx_close = spx["Close"]
    ma50  = spx_close.rolling(mcfg.ma_short).mean()
    ma200 = spx_close.rolling(mcfg.ma_long).mean()

    last_spx   = float(spx_close.iloc[-1])
    last_ma50  = float(ma50.iloc[-1])
    last_ma200 = float(ma200.iloc[-1])

    c1 = last_spx > last_ma50
    checks["spx_sobre_ma50"] = {
        "passed": c1,
        "value":  round(last_spx, 2),
        "target": round(last_ma50, 2),
        "note":   f"SPX {last_spx:.2f} vs MA50 {last_ma50:.2f}"
    }

    # ── 2. SPX sobre MA200 ────────────────────────────────────────────────
    c2 = last_spx > last_ma200
    checks["spx_sobre_ma200"] = {
        "passed": c2,
        "value":  round(last_spx, 2),
        "target": round(last_ma200, 2),
        "note":   f"SPX {last_spx:.2f} vs MA200 {last_ma200:.2f}"
    }

    # ── 3. Nasdaq sobre MA50 ──────────────────────────────────────────────
    c3 = False
    if nasdaq is not None and len(nasdaq) > mcfg.ma_short:
        qqq_close  = nasdaq["Close"]
        qqq_ma50   = qqq_close.rolling(mcfg.ma_short).mean()
        last_qqq   = float(qqq_close.iloc[-1])
        last_qma50 = float(qqq_ma50.iloc[-1])
        c3 = last_qqq > last_qma50
        checks["nasdaq_sobre_ma50"] = {
            "passed": c3,
            "value":  round(last_qqq, 2),
            "target": round(last_qma50, 2),
            "note":   f"QQQ {last_qqq:.2f} vs MA50 {last_qma50:.2f}"
        }
    else:
        checks["nasdaq_sobre_ma50"] = {
            "passed": False, "note": "Sin datos QQQ"
        }

    # ── 4. Días de distribución ───────────────────────────────────────────
    dist_days = _count_distribution_days(
        spx,
        window=mcfg.distribution_window,
        vol_mult=mcfg.distribution_vol_min
    )
    c4 = dist_days <= mcfg.distribution_max
    checks["dias_distribucion"] = {
        "passed": c4,
        "value":  dist_days,
        "target": mcfg.distribution_max,
        "note":   f"{dist_days} días de distribución (máx {mcfg.distribution_max})"
    }
    res.dist_days = dist_days

    # ── 5. Follow-Through Day ─────────────────────────────────────────────
    ftd = False
    if mcfg.ftd_required:
        ftd = _detect_ftd(
            spx,
            day_min=mcfg.ftd_window_start,
            day_max=mcfg.ftd_window_end,
            gain_min=mcfg.ftd_gain_min
        )
    else:
        ftd = True   # no requerido = siempre pasa

    c5 = ftd
    checks["follow_through_day"] = {
        "passed": c5,
        "note":   "FTD confirmado" if ftd else "Sin FTD reciente"
    }
    res.ftd_active = ftd

    # ── Score y resultado ─────────────────────────────────────────────────
    score  = sum([c1, c2, c3, c4, c5])
    # Mercado alcista: mínimo SPX sobre MA50 + MA200 + distribución OK
    passed = c1 and c2 and c4

    # Tendencia general
    if c1 and c2:
        trend = "alcista"
    elif not c1 and not c2:
        trend = "bajista"
    else:
        trend = "neutral"

    res.passed     = passed
    res.bullish    = passed
    res.score      = score
    res.details    = checks
    res.spx_trend  = trend
    res.note = (
        f"Mercado {trend} — {score}/5 checks · "
        f"SPX {last_spx:.0f} · Dist.days {dist_days} · "
        f"{'FTD ✓' if ftd else 'Sin FTD'}"
    )

    return res


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _count_distribution_days(df: pd.DataFrame, window: int,
                              vol_mult: float) -> int:
    """
    Días de distribución: sesión donde el índice CAJA (baja)
    con volumen >= vol_mult × día anterior.
    """
    if len(df) < window + 1:
        return 0

    recent = df.iloc[-(window + 1):]
    count  = 0
    closes  = recent["Close"].values
    volumes = recent["Volume"].values

    for i in range(1, len(closes)):
        if closes[i] < closes[i - 1] and volumes[i] >= volumes[i - 1] * vol_mult:
            count += 1

    return count


def _detect_ftd(df: pd.DataFrame, day_min: int, day_max: int,
                gain_min: float) -> bool:
    """
    Follow-Through Day: dentro de los últimos 25 sesiones,
    busca un día que suba >= gain_min con volumen > día anterior,
    ocurrido entre el día day_min y day_max de un intento de rally.

    Simplificado: buscamos en las últimas 20 sesiones un día
    con ganancia >= gain_min y vol > día anterior.
    """
    if len(df) < 20:
        return False

    recent  = df.iloc[-20:]
    closes  = recent["Close"].values
    volumes = recent["Volume"].values

    for i in range(1, len(closes)):
        gain = (closes[i] - closes[i - 1]) / closes[i - 1]
        if gain >= gain_min and volumes[i] > volumes[i - 1]:
            return True

    return False
