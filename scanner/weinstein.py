"""
weinstein.py — Detector de Weinstein Stage 2
=============================================
Portero #1 del pipeline. Si la acción no está en Stage 2,
retorna score=0 y el pipeline se detiene sin evaluar CANSLIM.

Stage 2 (avance) requiere:
  1. Precio de cierre > MA30 semanal
  2. MA30 semanal ascendente (pendiente positiva)
  3. MA30 > MA40 semanal
  4. Precio > MA200 diario (confirmación)
  5. Volumen en alzas > volumen en bajas (acumulación)
  6. No en Stage 4 (precio no bajo MA30 descendente)
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.weinstein")


@dataclass
class WeinsteinResult:
    passed:       bool         = False
    stage:        int          = 0       # 1, 2, 3 o 4
    score:        int          = 0       # 0–6
    max_score:    int          = 6
    details:      dict         = field(default_factory=dict)
    note:         str          = ""


def evaluate(price_data, cfg) -> WeinsteinResult:
    """
    Evalúa si una acción está en Weinstein Stage 2.

    Args:
        price_data: PriceData con .daily y .weekly
        cfg:        Config completo (usa cfg.weinstein)

    Returns:
        WeinsteinResult con passed=True si está en Stage 2
    """
    res = WeinsteinResult()
    wcfg = cfg.weinstein

    if price_data.error:
        res.note = f"Sin datos: {price_data.error}"
        return res

    weekly = price_data.weekly
    daily  = price_data.daily

    if weekly is None or len(weekly) < wcfg.ma_secondary_weeks + 5:
        res.note = "Datos semanales insuficientes"
        return res

    if daily is None or len(daily) < 210:
        res.note = "Datos diarios insuficientes"
        return res

    checks = {}

    # ── 1. MA30 y MA40 semanales ──────────────────────────────────────────
    weekly_close = weekly["Close"]
    ma30 = weekly_close.rolling(wcfg.ma_primary_weeks).mean()
    ma40 = weekly_close.rolling(wcfg.ma_secondary_weeks).mean()

    last_close_w = float(weekly_close.iloc[-1])
    last_ma30    = float(ma30.iloc[-1])
    last_ma40    = float(ma40.iloc[-1])

    # Check 1: precio > MA30 semanal
    c1 = last_close_w > last_ma30
    checks["precio_sobre_ma30"] = {
        "passed": c1,
        "value":  round(last_close_w, 2),
        "target": round(last_ma30, 2),
        "note":   f"Precio {last_close_w:.2f} vs MA30 {last_ma30:.2f}"
    }

    # Check 2: MA30 ascendente
    ma30_prev = float(ma30.iloc[-(wcfg.ma_slope_lookback + 1)])
    c2 = last_ma30 > ma30_prev
    checks["ma30_ascendente"] = {
        "passed": c2,
        "value":  round(last_ma30, 2),
        "target": round(ma30_prev, 2),
        "note":   f"MA30 actual {last_ma30:.2f} vs hace {wcfg.ma_slope_lookback}sem {ma30_prev:.2f}"
    }

    # Check 3: MA30 > MA40
    c3 = last_ma30 > last_ma40
    checks["ma30_sobre_ma40"] = {
        "passed": c3,
        "value":  round(last_ma30, 2),
        "target": round(last_ma40, 2),
        "note":   f"MA30 {last_ma30:.2f} vs MA40 {last_ma40:.2f}"
    }

    # ── 2. MA200 diario ───────────────────────────────────────────────────
    daily_close = daily["Close"]
    ma200       = daily_close.rolling(200).mean()
    last_close_d = float(daily_close.iloc[-1])
    last_ma200   = float(ma200.iloc[-1])

    c4 = last_close_d > last_ma200
    checks["precio_sobre_ma200_diario"] = {
        "passed": c4,
        "value":  round(last_close_d, 2),
        "target": round(last_ma200, 2),
        "note":   f"Precio {last_close_d:.2f} vs MA200 {last_ma200:.2f}"
    }

    # ── 3. Ratio volumen alcista / bajista ────────────────────────────────
    n_weeks  = wcfg.vol_ratio_weeks
    recent_w = weekly.iloc[-n_weeks:]

    up_vol   = 0.0
    down_vol = 0.0
    for _, row in recent_w.iterrows():
        try:
            c = float(row["Close"])
            o = float(row["Open"])
            v = float(row["Volume"])
            if c > o:
                up_vol += v
            elif c < o:
                down_vol += v
        except (KeyError, TypeError):
            pass

    vol_ratio = (up_vol / down_vol) if down_vol > 0 else 1.0
    c5 = vol_ratio >= wcfg.vol_ratio_min
    checks["vol_alcista_mayor"] = {
        "passed": c5,
        "value":  round(vol_ratio, 2),
        "target": wcfg.vol_ratio_min,
        "note":   f"Ratio vol alza/baja {vol_ratio:.2f} (mín {wcfg.vol_ratio_min})"
    }

    # ── 4. No Stage 4 ─────────────────────────────────────────────────────
    # Stage 4: precio < MA30 Y MA30 descendente
    is_stage4 = (last_close_w < last_ma30) and (last_ma30 < ma30_prev)
    c6 = not is_stage4
    checks["no_stage4"] = {
        "passed": c6,
        "value":  0 if is_stage4 else 1,
        "note":   "Stage 4 detectado — declive" if is_stage4 else "No en Stage 4"
    }

    # ── Score y Stage ─────────────────────────────────────────────────────
    passed_checks = [c1, c2, c3, c4, c5, c6]
    score = sum(passed_checks)

    # Determinar stage aproximado
    if is_stage4:
        stage = 4
    elif c1 and c2 and c3:
        stage = 2
    elif not c1 and not c2:
        stage = 1 if last_close_w > last_ma30 * 0.90 else 4
    else:
        stage = 3

    # Stage 2 requiere los 3 checks principales (1, 2, 3) más al menos 1 adicional
    passed = c1 and c2 and c3 and score >= 4

    res.passed  = passed
    res.stage   = stage
    res.score   = score
    res.details = checks
    res.note    = (
        f"Stage {stage} — {score}/6 checks · "
        f"Precio {last_close_d:.2f} · MA30w {last_ma30:.2f} · MA200d {last_ma200:.2f}"
    )

    return res
