"""
criteria_earnings_surprise.py — Earnings Surprise (O'Neil)
===========================================================
Fortalece el criterio C con el % de sorpresa vs estimados.

"Earnings surprises of 15–20%+ above estimates are a key
 accelerant of institutional buying — the real driver of big
 price moves." — William O'Neil

Scoring adicional al criterio C:
  surprise >= +15% → +2 puntos
  surprise >= +5%  → +1 punto
  surprise < 0%    → -2 puntos (miss penaliza fuerte)

Fuentes:
  FMP: endpoint /earnings-surprises/{ticker} (gratis, 250 req/día)
  yfinance: info.get("earningsQuarterlyGrowth") — aproximación
"""

import logging
import requests
from dataclasses import dataclass

logger = logging.getLogger("canslim.earnings_surprise")


@dataclass
class EarningsSurpriseResult:
    available:      bool  = False
    surprise_pct:   float = 0.0    # % de sorpresa más reciente
    beat:           bool  = False
    miss:           bool  = False
    score_modifier: int   = 0      # -2, 0, +1, o +2
    actual_eps:     float = 0.0
    estimated_eps:  float = 0.0
    note:           str   = ""


def evaluate_fmp(ticker: str, api_key: str) -> EarningsSurpriseResult:
    """Calcula earnings surprise usando FMP API."""
    res = EarningsSurpriseResult()

    if not api_key:
        res.note = "FMP_API_KEY no configurado"
        return res

    try:
        url = (f"https://financialmodelingprep.com/api/v3/"
               f"earnings-surprises/{ticker}?apikey={api_key}&limit=1")
        r   = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        if not data or not isinstance(data, list):
            res.note = "Sin datos de earnings surprise"
            return res

        latest = data[0]
        actual    = float(latest.get("actualEarningResult", 0) or 0)
        estimated = float(latest.get("estimatedEarning", 0) or 0)

        if estimated == 0:
            res.note = "Estimado = 0, no se puede calcular surprise"
            return res

        surprise = (actual - estimated) / abs(estimated) * 100

        # Score modifier
        if surprise >= 15:
            modifier = 2
        elif surprise >= 5:
            modifier = 1
        elif surprise < 0:
            modifier = -2
        else:
            modifier = 0

        res.available      = True
        res.surprise_pct   = round(surprise, 1)
        res.beat           = surprise >= 5
        res.miss           = surprise < 0
        res.score_modifier = modifier
        res.actual_eps     = round(actual, 3)
        res.estimated_eps  = round(estimated, 3)
        res.note = (
            f"Surprise {surprise:+.1f}% "
            f"(actual {actual:.3f} vs est {estimated:.3f}) → "
            f"score {'+' if modifier >= 0 else ''}{modifier}"
        )

    except Exception as exc:
        res.note = f"Error FMP earnings surprise: {exc}"
        logger.debug(f"{ticker} surprise: {exc}")

    return res


def evaluate_yfinance(fund_data) -> EarningsSurpriseResult:
    """
    Aproximación usando yfinance cuando no hay FMP.
    Compara EPS real vs estimado de los datos del fetcher.
    """
    res = EarningsSurpriseResult()

    if (not fund_data
            or not fund_data.quarterly_eps
            or not fund_data.quarterly_eps_estimate):
        res.note = "Sin datos de estimados (usa FMP para datos precisos)"
        return res

    actual    = fund_data.quarterly_eps[0]
    estimated = fund_data.quarterly_eps_estimate[0]

    if not estimated or estimated == 0:
        res.note = "Sin estimado disponible"
        return res

    surprise = (actual - estimated) / abs(estimated) * 100

    if surprise >= 15:
        modifier = 2
    elif surprise >= 5:
        modifier = 1
    elif surprise < 0:
        modifier = -2
    else:
        modifier = 0

    res.available      = True
    res.surprise_pct   = round(surprise, 1)
    res.beat           = surprise >= 5
    res.miss           = surprise < 0
    res.score_modifier = modifier
    res.actual_eps     = round(actual, 3)
    res.estimated_eps  = round(estimated, 3)
    res.note = (
        f"Surprise {surprise:+.1f}% → "
        f"score {'+' if modifier >= 0 else ''}{modifier}"
    )

    return res


def evaluate(ticker: str, fund_data, cfg) -> EarningsSurpriseResult:
    """
    Punto de entrada: usa FMP si hay API key, sino yfinance.
    """
    if cfg.pipeline.fmp_api_key:
        return evaluate_fmp(ticker, cfg.pipeline.fmp_api_key)
    return evaluate_yfinance(fund_data)
