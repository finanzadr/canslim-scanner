"""
universe.py — Universos de tickers
====================================
Carga listas de tickers para escanear.
"""

import re
import urllib.request
from pathlib import Path


_DEFAULT = [
    # Tecnología — líderes de mercado
    "NVDA", "AAPL", "MSFT", "META", "GOOGL", "AMZN", "AVGO", "AMD",
    "CRM", "NOW", "SNOW", "DDOG", "NET", "CRWD", "ZS", "PANW",
    "ANET", "FTNT", "KLAC", "LRCX", "AMAT", "SMCI", "ARM", "PLTR",
    # Consumo / Retail
    "COST", "DECK", "LULU", "ONON", "ELF", "CELH", "AXON",
    # Salud / Biotech
    "LLY", "NVO", "ISRG", "DXCM", "PODD", "RXRX", "ROIV",
    # Financiero / Fintech
    "V", "MA", "PYPL", "COIN", "HOOD", "AFRM",
    # Energía / Industria
    "XOM", "OXY", "URI", "PWR", "CIEN", "GNRC",
    # Comunicaciones / Ocio
    "NFLX", "SPOT", "TTD", "ROKU", "BKNG", "ABNB", "UBER",
    # Small/Mid cap momentum
    "ASTS", "IONQ", "RKLB", "JOBY", "ACHR",
]


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

    if name == "sp500":
        return _scrape_wikipedia(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            col_index=0, label="S&P 500"
        )

    if name == "nasdaq100":
        return _scrape_wikipedia(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            col_index=1, label="Nasdaq 100"
        )

    return _DEFAULT


def _scrape_wikipedia(url: str, col_index: int, label: str) -> list[str]:
    print(f"  Descargando universo {label}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
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
        print(f"  {len(tickers)} tickers en {label}")
        return tickers or _DEFAULT

    except Exception as exc:
        print(f"  Error descargando {label}: {exc} — usando universo default")
        return _DEFAULT
