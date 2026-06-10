"""
criteria_sector.py — Sector ETF en Weinstein Stage 2
=====================================================
Filtro ELIMINATORIO (Weinstein cap. 3):
"Always check the sector before the stock.
 A stock fighting a declining group is swimming upstream."

Si el sector está en Stage 3 o 4, el trade tiene 70% de fracaso
sin importar qué tan buena sea la acción individual.
"""

import logging
import yfinance as yf
import pandas as pd
from dataclasses import dataclass, field

logger = logging.getLogger("canslim.sector")

# Mapeo sector (yfinance) → ETF sectorial
SECTOR_TO_ETF = {
    "Technology":              "XLK",
    "Health Care":             "XLV",
    "Consumer Discretionary":  "XLY",
    "Consumer Staples":        "XLP",
    "Financials":              "XLF",
    "Energy":                  "XLE",
    "Materials":               "XLB",
    "Industrials":             "XLI",
    "Communication Services":  "XLC",
    "Utilities":               "XLU",
    "Real Estate":             "XLRE",
    # Subsectores específicos
    "Biotechnology":           "XBI",
    "Semiconductors":          "SOXX",
    "Software":                "IGV",
    "Banks":                   "KBE",
    "Retail":                  "XRT",
}


@dataclass
class SectorResult:
    passed:       bool  = False
    etf:          str   = ""
    stage:        int   = 0
    ma30_slope:   float = 0.0
    price_vs_ma30:float = 0.0
    note:         str   = ""


def evaluate(sector: str, sector_cache: dict, cfg) -> SectorResult:
    """
    Evalúa si el sector de la acción está en Weinstein Stage 2.

    Args:
        sector:       Nombre del sector (campo de yfinance)
        sector_cache: Dict {sector_name: DataFrame semanal} precargado
        cfg:          Config completo

    Returns:
        SectorResult con passed=True si el sector está en Stage 2
    """
    res = SectorResult()

    etf = SECTOR_TO_ETF.get(sector, "SPY")
    res.etf = etf

    # Buscar en caché
    weekly = sector_cache.get(sector) or sector_cache.get(etf)

    if weekly is None or len(weekly) < 35:
        # Sin datos de sector — usar SPY como fallback (no penalizar)
        res.passed = True
        res.note   = f"Sin datos de sector ETF ({etf}) — no penalizado"
        return res

    sector_close = weekly["Close"]
    ma30 = sector_close.rolling(30).mean()
    ma40 = sector_close.rolling(40).mean()

    last_close = float(sector_close.iloc[-1])
    last_ma30  = float(ma30.iloc[-1])
    last_ma40  = float(ma40.iloc[-1])
    prev_ma30  = float(ma30.iloc[-5]) if len(ma30) > 5 else last_ma30

    price_above_ma30 = last_close > last_ma30
    ma30_rising      = last_ma30 > prev_ma30
    ma30_above_ma40  = last_ma30 > last_ma40

    # Stage 2: precio > MA30 ascendente > MA40
    is_stage2 = price_above_ma30 and ma30_rising and ma30_above_ma40

    # Stage 4: precio < MA30 descendente (peor caso)
    is_stage4 = (last_close < last_ma30) and (last_ma30 < prev_ma30)

    stage = 2 if is_stage2 else (4 if is_stage4 else 3)

    slope_pct    = (last_ma30 - prev_ma30) / prev_ma30 * 100 if prev_ma30 > 0 else 0
    price_vs_ma  = (last_close - last_ma30) / last_ma30 * 100 if last_ma30 > 0 else 0

    res.passed       = is_stage2
    res.stage        = stage
    res.ma30_slope   = round(slope_pct, 2)
    res.price_vs_ma30 = round(price_vs_ma, 1)
    res.note = (
        f"Sector {sector} ({etf}) Stage {stage} · "
        f"Precio {'+' if price_vs_ma >= 0 else ''}{price_vs_ma:.1f}% vs MA30 · "
        f"MA30 {'↑' if ma30_rising else '↓'} {slope_pct:+.2f}%/sem"
    )

    return res


def preload_sector_etfs(sectors: list[str], cfg) -> dict:
    """
    Precarga datos semanales de todos los ETFs sectoriales necesarios.
    Retorna {sector_name: DataFrame_semanal}.
    """
    needed_etfs = {}
    for sector in set(sectors):
        etf = SECTOR_TO_ETF.get(sector, "SPY")
        needed_etfs[etf] = sector

    cache = {}
    for etf, sector in needed_etfs.items():
        try:
            df = yf.Ticker(etf).history(
                period="1y", interval="1wk", auto_adjust=True
            )
            if not df.empty:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                cache[sector] = df
                cache[etf]    = df   # también por ticker
        except Exception as exc:
            logger.debug(f"sector ETF {etf}: {exc}")

    logger.info(f"Sectores precargados: {len(cache)}")
    return cache
