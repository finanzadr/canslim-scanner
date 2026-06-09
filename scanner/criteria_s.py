"""
criteria_s.py — Supply & Demand (S)
=====================================
Evalúa la presión compradora institucional y la flotación.

Sub-criterios:
  S1 — Días de acumulación > distribución (últimas 13 semanas)
  S2 — Ratio volumen alcista / bajista >= 1.2 (últimas 50 sesiones)
  S3 — Flotación < 100M acciones
  S4 — Shares outstanding cayendo YoY (recompras)
"""

import logging
import pandas as pd
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.criteria_s")


@dataclass
class CriteriaSResult:
    passed:       bool  = False
    score:        int   = 0
    max_score:    int   = 4
    details:      dict  = field(default_factory=dict)
    note:         str   = ""

    acc_days:     int   = 0
    dist_days:    int   = 0
    upvol_ratio:  float = 0.0
    float_shares: float = 0.0
    buybacks:     bool  = False


def evaluate(price_data, fund_data, cfg) -> CriteriaSResult:
    res  = CriteriaSResult()
    scfg = cfg.s

    if price_data.error or price_data.daily is None:
        res.note = f"Sin datos de precio: {price_data.error}"
        return res

    daily  = price_data.daily
    checks = {}

    close  = daily["Close"].values
    volume = daily["Volume"].values
    opens  = daily["Open"].values

    # ── S1 — Días acumulación vs distribución (13 semanas = ~65 sesiones) ─
    window_s1 = scfg.acc_dist_weeks * 5
    window_s1 = min(window_s1, len(close) - 1)

    acc_days  = 0
    dist_days = 0
    for i in range(1, window_s1 + 1):
        idx = len(close) - i
        if idx < 1:
            break
        price_up   = close[idx] > close[idx - 1]
        vol_heavy  = volume[idx] > volume[idx - 1] * 0.9

        if price_up and vol_heavy:
            acc_days += 1
        elif not price_up and vol_heavy:
            dist_days += 1

    acc_ratio = acc_days / dist_days if dist_days > 0 else acc_days
    c1 = acc_ratio >= scfg.acc_dist_ratio_min and acc_days > dist_days

    checks["S1_acumulacion_vs_distribucion"] = {
        "passed": c1,
        "value":  round(acc_ratio, 2),
        "target": scfg.acc_dist_ratio_min,
        "note":   f"Acum {acc_days}d vs Dist {dist_days}d · ratio {acc_ratio:.2f}"
    }
    res.acc_days  = acc_days
    res.dist_days = dist_days

    # ── S2 — Ratio volumen alcista / bajista ──────────────────────────────
    n50     = min(scfg.upvol_downvol_sessions, len(close) - 1)
    up_vol  = 0.0
    dn_vol  = 0.0

    for i in range(1, n50 + 1):
        idx = len(close) - i
        if idx < 0:
            break
        v = float(volume[idx])
        if close[idx] > opens[idx]:
            up_vol += v
        elif close[idx] < opens[idx]:
            dn_vol += v

    uv_ratio = up_vol / dn_vol if dn_vol > 0 else 1.0
    c2 = uv_ratio >= scfg.upvol_downvol_min

    checks["S2_vol_alcista_vs_bajista"] = {
        "passed": c2,
        "value":  round(uv_ratio, 2),
        "target": scfg.upvol_downvol_min,
        "note":   f"Up-vol/Down-vol {uv_ratio:.2f} (mín {scfg.upvol_downvol_min})"
    }
    res.upvol_ratio = round(uv_ratio, 2)

    # ── S3 — Flotación ────────────────────────────────────────────────────
    float_sh = fund_data.float_shares if fund_data else 0.0
    c3 = float_sh > 0 and float_sh <= scfg.float_max_shares

    if float_sh > 0:
        float_m = float_sh / 1e6
        note_s3 = f"Flotación {float_m:.1f}M (máx {scfg.float_max_shares/1e6:.0f}M)"
        if float_sh <= scfg.float_small_bonus:
            note_s3 += " ★ flotación pequeña"
    else:
        note_s3 = "Sin datos de flotación"

    checks["S3_flotacion"] = {
        "passed": c3,
        "value":  round(float_sh / 1e6, 1) if float_sh > 0 else 0,
        "target": scfg.float_max_shares / 1e6,
        "note":   note_s3
    }
    res.float_shares = float_sh

    # ── S4 — Recompras (shares outstanding cayendo) ───────────────────────
    c4 = False
    if fund_data and len(fund_data.annual_shares) >= 2:
        curr_sh = fund_data.annual_shares[0]
        prev_sh = fund_data.annual_shares[1]
        if prev_sh and prev_sh > 0:
            change = (curr_sh - prev_sh) / prev_sh
            c4     = change < 0   # cayó = recompras
            checks["S4_recompras"] = {
                "passed": c4,
                "value":  round(change * 100, 1),
                "note":   f"Shares {'↓' if c4 else '↑'} {change*100:+.1f}% YoY"
            }
            res.buybacks = c4
        else:
            checks["S4_recompras"] = {"passed": False, "note": "Sin datos previos"}
    else:
        checks["S4_recompras"] = {"passed": False, "note": "Sin datos de shares"}

    # ── Score ─────────────────────────────────────────────────────────────
    score      = sum([c1, c2, c3, c4])
    res.passed  = score >= 3
    res.score   = score
    res.details = checks
    res.note = (
        f"S: {score}/4 — "
        f"Acum/Dist {acc_days}/{dist_days} · "
        f"UpVol {uv_ratio:.1f}x · "
        f"Float {float_sh/1e6:.0f}M"
    )
    return res
