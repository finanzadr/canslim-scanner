"""
criteria_n.py — New high / Breakout (N)
========================================
Detecta rupturas de base con volumen y zonas de nuevo máximo.

Sub-criterios:
  N1 — Precio >= 95% del máximo 52 semanas
  N2 — Ruptura de base con volumen >= 1.4x MA50
  N3 — Base válida detectada (25-65 barras, profundidad 10-33%)
  N4 — No extendida (precio < 5% sobre el buy point)
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.criteria_n")


@dataclass
class CriteriaNResult:
    passed:       bool  = False
    score:        int   = 0
    max_score:    int   = 4
    details:      dict  = field(default_factory=dict)
    note:         str   = ""

    # Valores clave para la app web
    near_52w_high:    bool  = False
    breakout_signal:  bool  = False
    base_detected:    bool  = False
    not_extended:     bool  = False
    buy_point:        float = 0.0
    vol_ratio:        float = 0.0


def evaluate(price_data, cfg) -> CriteriaNResult:
    res  = CriteriaNResult()
    ncfg = cfg.n

    if price_data.error or price_data.daily is None:
        res.note = f"Sin datos de precio: {price_data.error}"
        return res

    daily = price_data.daily
    if len(daily) < 60:
        res.note = "Datos insuficientes (< 60 barras)"
        return res

    checks = {}
    close  = daily["Close"]
    high   = daily["High"]
    volume = daily["Volume"]

    # ── N1 — Cerca del máximo 52 semanas ─────────────────────────────────
    high_52w    = float(high.iloc[-252:].max()) if len(high) >= 252 else float(high.max())
    last_close  = float(close.iloc[-1])
    proximity   = last_close / high_52w if high_52w > 0 else 0.0
    new_52w     = last_close >= high_52w * 0.999

    c1 = proximity >= ncfg.high_52w_proximity
    checks["N1_cerca_maximo_52w"] = {
        "passed": c1,
        "value":  round(proximity * 100, 1),
        "target": round(ncfg.high_52w_proximity * 100, 1),
        "note":   f"Precio {last_close:.2f} es {proximity*100:.1f}% del máx 52w {high_52w:.2f}"
                  + (" ★ Nuevo máximo" if new_52w else "")
    }
    res.near_52w_high = c1

    # ── N2 — Ruptura con volumen ──────────────────────────────────────────
    vol_ma50   = float(volume.rolling(50).mean().iloc[-1])
    last_vol   = float(volume.iloc[-1])
    vol_ratio  = last_vol / vol_ma50 if vol_ma50 > 0 else 0.0

    # Buy point = máximo de los últimos pivot_lookback barras
    pivot_lb   = 10
    pivot_high = float(high.iloc[-pivot_lb - 1:-1].max())
    buy_point  = pivot_high * (1 + ncfg.pivot_buffer)

    bullish_bar = float(close.iloc[-1]) > float(daily["Open"].iloc[-1])
    breakout    = (last_close > buy_point
                   and vol_ratio >= ncfg.breakout_vol_mult
                   and bullish_bar)

    c2 = breakout
    checks["N2_ruptura_con_volumen"] = {
        "passed": c2,
        "value":  round(vol_ratio, 2),
        "target": ncfg.breakout_vol_mult,
        "note": (
            f"Vol {vol_ratio:.1f}x MA50 · "
            f"Precio {last_close:.2f} vs buy point {buy_point:.2f} · "
            f"{'Barra alcista ✓' if bullish_bar else 'Barra bajista'}"
        )
    }
    res.breakout_signal = c2
    res.buy_point       = round(buy_point, 2)
    res.vol_ratio       = round(vol_ratio, 2)

    # ── N3 — Base válida ──────────────────────────────────────────────────
    base_found, base_info = _detect_base(
        close, high, daily["Low"],
        min_bars=ncfg.base_min_bars,
        max_bars=ncfg.base_max_bars,
        depth_min=ncfg.base_depth_min,
        depth_max=ncfg.base_depth_max,
    )
    c3 = base_found
    checks["N3_base_valida"] = {
        "passed": c3,
        "note":   base_info
    }
    res.base_detected = c3

    # ── N4 — No extendida ─────────────────────────────────────────────────
    extension   = (last_close - buy_point) / buy_point if buy_point > 0 else 1.0
    c4          = extension <= ncfg.max_extension
    checks["N4_no_extendida"] = {
        "passed": c4,
        "value":  round(extension * 100, 1),
        "target": round(ncfg.max_extension * 100, 1),
        "note":   f"Extensión {extension*100:.1f}% sobre buy point (máx {ncfg.max_extension*100:.0f}%)"
    }
    res.not_extended = c4

    # ── Score ─────────────────────────────────────────────────────────────
    score      = sum([c1, c2, c3, c4])
    res.passed  = score >= 3
    res.score   = score
    res.details = checks
    res.note = (
        f"N: {score}/4 — "
        f"{'52w ✓' if c1 else '52w ✗'} · "
        f"{'Ruptura ✓' if c2 else 'Ruptura ✗'} · "
        f"{'Base ✓' if c3 else 'Sin base'} · "
        f"{'No ext ✓' if c4 else 'Extendida'}"
    )
    return res


def _detect_base(close, high, low,
                 min_bars, max_bars, depth_min, depth_max):
    """
    Busca una base válida en las últimas max_bars barras.
    Retorna (found: bool, description: str).
    """
    if len(close) < min_bars + 10:
        return False, "Datos insuficientes para detectar base"

    closes = close.values
    highs  = high.values
    lows   = low.values
    n      = len(closes)

    # Buscar desde el final hacia atrás
    for start in range(n - max_bars, n - min_bars):
        if start < 0:
            continue

        segment_high = float(np.max(highs[start:n]))
        segment_low  = float(np.min(lows[start:n]))

        if segment_high == 0:
            continue

        depth = (segment_high - segment_low) / segment_high
        dur   = n - start

        if depth_min <= depth <= depth_max and min_bars <= dur <= max_bars:
            # Verificar que el precio actual esté cerca del techo de la base
            current      = float(closes[-1])
            pct_of_top   = current / segment_high
            if pct_of_top >= 0.90:
                return True, (
                    f"Base de {dur} barras · "
                    f"profundidad {depth*100:.1f}% · "
                    f"precio en {pct_of_top*100:.1f}% del techo"
                )

    return False, "Sin base válida en el rango buscado"
