"""
criteria_entry.py — Parámetros de entrada (Minervini)
======================================================
Convierte el score en una herramienta de decisión real.

Calcula:
  - Pivot point  : máximo de la base + 0.5% buffer
  - Stop técnico : 7–8% bajo el pivot (Minervini/O'Neil)
  - Target 1R/2R/3R : múltiplos del riesgo
  - Base tightness : qué tan apretada es la base (< 25% = válida)
  - Risk % : cuánto arriesgas en el trade

"A setup without an entry, stop, and target is just a stock you like."
— Mark Minervini
"""

import logging
import numpy as np
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.entry")


@dataclass
class EntryParams:
    valid:          bool  = False   # hay setup de entrada válido
    pivot:          float = 0.0     # buy point exacto
    stop:           float = 0.0     # stop loss
    target_1r:      float = 0.0     # target 1:1
    target_2r:      float = 0.0     # target 1:2
    target_3r:      float = 0.0     # target 1:3 (objetivo principal)
    risk_pct:       float = 0.0     # % de riesgo desde pivot al stop
    rr_ratio:       float = 0.0     # R:R hasta target_3r
    base_weeks:     int   = 0       # duración de la base en semanas
    base_tightness: float = 0.0     # rango de la base en %
    base_type:      str   = ""      # "tight" | "normal" | "loose"
    current_price:  float = 0.0     # precio actual
    extended_pct:   float = 0.0     # % sobre el pivot (si ya rompió)
    actionable:     bool  = False   # precio aún dentro del rango de compra
    note:           str   = ""


def calculate(price_data, cfg) -> EntryParams:
    """
    Calcula los parámetros de entrada usando datos semanales.

    Lógica Minervini/O'Neil:
      1. Detectar base en las últimas N semanas (rango < 25%)
      2. Pivot = máximo de la base × 1.005
      3. Stop  = pivot × (1 - stop_pct)
      4. Targets = pivot + (pivot - stop) × múltiplo
      5. Accionable si precio actual <= pivot × 1.03 (dentro del 3%)
    """
    res = EntryParams()

    if price_data.error or price_data.weekly is None or price_data.daily is None:
        res.note = "Sin datos de precio"
        return res

    weekly = price_data.weekly
    daily  = price_data.daily

    if len(weekly) < 10:
        res.note = "Datos semanales insuficientes"
        return res

    ecfg = cfg.n   # reutiliza parámetros del criterio N
    stop_pct = 0.08   # Minervini: stop 8% bajo el pivot

    current_price = float(daily["Close"].iloc[-1])
    res.current_price = round(current_price, 2)

    # Buscar base válida (de más larga a más corta — preferimos la más reciente)
    best = None
    for lookback in [15, 12, 10, 8]:
        if len(weekly) < lookback:
            continue

        w_highs  = weekly["High"].iloc[-lookback:].values
        w_lows   = weekly["Low"].iloc[-lookback:].values
        w_closes = weekly["Close"].iloc[-lookback:].values

        base_high = float(np.max(w_highs))
        base_low  = float(np.min(w_lows))

        if base_low == 0:
            continue

        tightness = (base_high - base_low) / base_low

        # Base válida: rango < 35% (hasta 25% = tight, 25–35% = normal)
        if tightness <= 0.35:
            best = {
                "high":      base_high,
                "low":       base_low,
                "tightness": tightness,
                "weeks":     lookback,
            }
            break   # tomamos la más larga que sea válida

    if best is None:
        res.note = "Sin base válida (rango > 35% en todas las ventanas)"
        return res

    # Pivot y stop
    pivot    = round(best["high"] * 1.005, 2)
    stop     = round(pivot * (1 - stop_pct), 2)
    risk_amt = pivot - stop

    if risk_amt <= 0:
        res.note = "Error calculando riesgo"
        return res

    # Targets
    t1 = round(pivot + risk_amt * 1, 2)
    t2 = round(pivot + risk_amt * 2, 2)
    t3 = round(pivot + risk_amt * 3, 2)

    # ¿Precio actual accionable? (dentro del 3% sobre el pivot)
    extended     = (current_price - pivot) / pivot if pivot > 0 else 0
    actionable   = -0.05 <= extended <= 0.03   # entre -5% (pre-ruptura) y +3%

    # Tipo de base
    t = best["tightness"]
    if t <= 0.12:
        base_type = "tight ★"       # < 12% = muy apretada, señal fuerte
    elif t <= 0.20:
        base_type = "normal"
    elif t <= 0.25:
        base_type = "normal-amplia"
    else:
        base_type = "amplia"

    res.valid          = True
    res.pivot          = pivot
    res.stop           = stop
    res.target_1r      = t1
    res.target_2r      = t2
    res.target_3r      = t3
    res.risk_pct       = round(stop_pct * 100, 1)
    res.rr_ratio       = 3.0
    res.base_weeks     = best["weeks"]
    res.base_tightness = round(t * 100, 1)
    res.base_type      = base_type
    res.extended_pct   = round(extended * 100, 1)
    res.actionable     = actionable
    res.note = (
        f"Pivot {pivot} · Stop {stop} (-{stop_pct*100:.0f}%) · "
        f"Target 3R: {t3} · Base {best['weeks']}w {base_type} "
        f"({t*100:.1f}%) · "
        f"{'✓ Accionable' if actionable else f'Extendido +{extended*100:.1f}%'}"
    )

    return res


def to_dict(entry: EntryParams) -> dict:
    """Serializa para el JSON de resultados."""
    if not entry.valid:
        return {"valid": False, "note": entry.note}
    return {
        "valid":          entry.valid,
        "pivot":          entry.pivot,
        "stop":           entry.stop,
        "target_1r":      entry.target_1r,
        "target_2r":      entry.target_2r,
        "target_3r":      entry.target_3r,
        "risk_pct":       entry.risk_pct,
        "rr_ratio":       entry.rr_ratio,
        "base_weeks":     entry.base_weeks,
        "base_tightness": entry.base_tightness,
        "base_type":      entry.base_type,
        "current_price":  entry.current_price,
        "extended_pct":   entry.extended_pct,
        "actionable":     entry.actionable,
        "note":           entry.note,
    }
