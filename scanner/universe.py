"""
universe.py — Universos de tickers
====================================
Universos disponibles:
  default    : líderes curados (~62 acciones)
  sp500      : S&P 500 completo (~500)
  nasdaq100  : Nasdaq 100 (~100)
  sp500_nasdaq: S&P 500 + Nasdaq 100 deduplicado (~550) ← RECOMENDADO
  combined   : S&P 500 + Nasdaq 100 + Russell 1000 (~800)
  custom     : custom_universe.txt (uno por línea)
"""

import re
import urllib.request
from pathlib import Path


_DEFAULT = [
    "NVDA", "AAPL", "MSFT", "META", "GOOGL", "AMZN", "AVGO", "AMD",
    "CRM", "NOW", "SNOW", "DDOG", "NET", "CRWD", "ZS", "PANW",
    "ANET", "FTNT", "KLAC", "LRCX", "AMAT", "SMCI", "ARM", "PLTR",
    "COST", "DECK", "LULU", "ONON", "ELF", "CELH", "AXON",
    "LLY", "NVO", "ISRG", "DXCM", "PODD", "RXRX",
    "V", "MA", "PYPL", "COIN", "HOOD", "AFRM",
    "XOM", "OXY", "URI", "PWR", "CIEN", "GNRC",
    "NFLX", "SPOT", "TTD", "ROKU", "BKNG", "ABNB", "UBER",
    "ASTS", "IONQ", "RKLB", "JOBY", "ACHR",
]

_WIKI_SOURCES = {
    "sp500": (
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        0, "S&P 500"
    ),
    "nasdaq100": (
        "https://en.wikipedia.org/wiki/Nasdaq-100",
        1, "Nasdaq 100"
    ),
    "russell1000": (
        "https://en.wikipedia.org/wiki/Russell_1000_Index",
        0, "Russell 1000"
    ),
}


def load_universe(name: str) -> list[str]:
    if name == "default":
        return _DEFAULT

    if name == "custom":
        path = Path("custom_universe.txt")
        if not path.exists():
            raise FileNotFoundError(
                "Crea 'custom_universe.txt' con un ticker por línea."
            )
        tickers = [
            line.strip().upper()
            for line in path.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        print(f"  Universo custom: {len(tickers)} tickers")
        return tickers

    if name == "sp500_nasdaq":
        return _load_sp500_nasdaq()

    if name == "combined":
        return _load_combined(["sp500", "nasdaq100", "russell1000"])

    if name in _WIKI_SOURCES:
        url, col, label = _WIKI_SOURCES[name]
        return _scrape_wikipedia(url, col, label)

    return _DEFAULT


def _load_sp500_nasdaq() -> list[str]:
    """
    S&P 500 + Nasdaq 100 deduplicado — ~550 tickers.
    Cubre el 90%+ de los setups CANSLIM reales.
    Tiempo estimado: ~8 minutos con 8 workers.
    """
    print("  Construyendo universo S&P 500 + Nasdaq 100...")
    return _load_combined(["sp500", "nasdaq100"])


def _load_combined(sources: list[str]) -> list[str]:
    all_tickers = []
    for name in sources:
        url, col, label = _WIKI_SOURCES[name]
        batch = _scrape_wikipedia(url, col, label)
        all_tickers.extend(batch)

    seen   = set()
    unique = []
    for t in all_tickers:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    # Solo letras, 1–5 caracteres (filtra artefactos del scraping)
    unique = [t for t in unique if 1 <= len(t) <= 5 and t.isalpha()]

    print(f"  Total: {len(unique)} tickers únicos")
    return unique


def _scrape_wikipedia(url: str, col_index: int, label: str) -> list[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        rows    = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
        tickers = []
        for row in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
            if len(cells) > col_index:
                raw    = re.sub(r"<[^>]+>", "", cells[col_index]).strip()
                ticker = re.sub(r"[^A-Z.\-]", "", raw.upper()).replace(".", "-")
                if 1 <= len(ticker) <= 6:
                    tickers.append(ticker)

        tickers = list(dict.fromkeys(tickers))
        print(f"  {label}: {len(tickers)} tickers")
        return tickers or _DEFAULT

    except Exception as exc:
        print(f"  Error descargando {label}: {exc} — usando default")
        return _DEFAULT
