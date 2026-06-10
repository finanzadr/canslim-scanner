"""
runner.py — Orquestador del pipeline CANSLIM
=============================================
Corre el pipeline completo:
  1. Verifica mercado (M) — si falla, termina
  2. Para cada ticker:
     a. Descarga precios y fundamentales
     b. Verifica Weinstein Stage 2
     c. Evalúa C, A, N, S, L, I
     d. Calcula score total
  3. Guarda resultados en JSON
  4. Exporta watchlist para TradingView

Uso:
  python -m scanner.runner
  python -m scanner.runner --tickers NVDA AAPL MSFT
  python -m scanner.runner --universe sp500
"""

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .config      import cfg, Config
from .fetcher     import get_fetcher
from .universe    import load_universe
from .weinstein   import evaluate as eval_weinstein
from .criteria_m  import evaluate as eval_m
from .criteria_c  import evaluate as eval_c
from .criteria_a  import evaluate as eval_a
from .criteria_n  import evaluate as eval_n
from .criteria_s  import evaluate as eval_s
from .criteria_l  import evaluate as eval_l, _calc_rs
from .criteria_i  import evaluate as eval_i
from .scorer      import build_result, ScanResult

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("canslim.runner")

# ═══════════════════════════════════════════════════════════════════════════════
#  PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def run(config: Config = None, tickers: list = None, universe: str = "default",
        verbose: bool = False) -> list[ScanResult]:

    config   = config or cfg
    fetcher  = get_fetcher(config)

    if verbose:
        logging.getLogger("canslim").setLevel(logging.INFO)

    # ── 1. Universo ────────────────────────────────────────────────────────
    if tickers:
        symbols = [t.upper() for t in tickers]
    else:
        symbols = load_universe(universe)

    total = len(symbols)
    print(f"\n  CANSLIM Scanner + Weinstein Stage 2")
    print(f"  {'─' * 40}")
    print(f"  Universo: {total} tickers  |  Fuente: {config.pipeline.data_source}")
    print(f"  Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n")

    # ── 2. Verificar mercado (M) ───────────────────────────────────────────
    print("  [1/3] Verificando dirección del mercado...")
    market_data = fetcher.fetch_market(
        config.market.spx_ticker,
        config.market.nasdaq_ticker
    )
    market_res = eval_m(market_data, config)

    print(f"        {market_res.note}")
    if not market_res.passed:
        print(f"\n  ⚠ Mercado no alcista — scanner pausado.")
        print(f"  No se procesarán acciones hasta que el mercado confirme tendencia.\n")
        _save_results([], config, market_blocked=True,
                      market_note=market_res.note)
        return []

    print(f"  ✓ Mercado alcista\n")

    # ── 3. Descargar sector ETFs ───────────────────────────────────────────
    sector_cache = {}
    if config.l.require_sector_stage2:
        print("  [2/3] Descargando datos de sectores...")
        import yfinance as yf
        for sector, etf in config.l.sector_etfs.items():
            try:
                df = yf.Ticker(etf).history(period="1y", interval="1wk",
                                             auto_adjust=True)
                if not df.empty:
                    sector_cache[sector] = df
            except Exception:
                pass
        print(f"        {len(sector_cache)} sectores cargados\n")

    # ── 4. Escanear tickers en paralelo ────────────────────────────────────
    print(f"  [3/3] Escaneando {total} tickers...")
    results  = []
    done     = 0

    # Primera pasada: calcular RS para todos (necesario para percentiles)
    rs_values = {}

    def analyze(ticker: str) -> ScanResult:
        try:
            prices = fetcher.fetch_prices(ticker)
            funds  = fetcher.fetch_fundamentals(ticker)

            # Weinstein — portero #1
            w_res = eval_weinstein(prices, config)
            if not w_res.passed:
                return build_result(ticker, funds, w_res, market_res,
                                    None, None, None, None, None, None, config)

            # Criterios CANSLIM
            c_res = eval_c(funds, config)
            a_res = eval_a(funds, config)
            n_res = eval_n(prices, config)
            s_res = eval_s(prices, funds, config)

            # L — RS con sector
            sector_df = sector_cache.get(funds.sector) if funds else None
            l_res = eval_l(prices, market_data.spx, sector_df,
                           list(rs_values.values()), config)
            rs_values[ticker] = l_res.rs_value   # guardar para percentiles

            i_res = eval_i(funds, config)

            return build_result(ticker, funds, w_res, market_res,
                                c_res, a_res, n_res, s_res, l_res, i_res, config)

        except Exception as exc:
            logger.error(f"{ticker}: {exc}")
            res = ScanResult(ticker=ticker, error=str(exc))
            return res

    with ThreadPoolExecutor(max_workers=config.pipeline.workers) as pool:
        futures = {pool.submit(analyze, t): t for t in symbols}
        for fut in as_completed(futures):
            res   = fut.result()
            done += 1
            results.append(res)
            _print_progress(done, total, res)

    print(f"\n\n  {'─' * 40}")

    # ── 5. Filtrar y ordenar ───────────────────────────────────────────────
    passing = [r for r in results if r.passes_filter]
    passing.sort(key=lambda r: r.score, reverse=True)

    errors  = sum(1 for r in results if r.error and not r.weinstein_passed)
    blocked = sum(1 for r in results if not r.weinstein_passed and not r.error)

    print(f"  Total: {total}  |  Stage 2: {total - blocked}  "
          f"|  Pasan filtro: {len(passing)}  |  Errores: {errors}\n")

    # ── 6. Reporte consola ─────────────────────────────────────────────────
    if passing:
        print(f"  {'#':<4} {'Ticker':<8} {'Score':<8} {'Grade':<8} "
              f"{'EPS%':<8} {'ROE%':<7} {'RS':<7} {'Sector'}")
        print(f"  {'─' * 68}")
        for i, r in enumerate(passing, 1):
            grade_icon = {"elite": "★★", "strong": "★", "valid": "✓"}.get(r.grade, "")
            print(
                f"  {i:<4} {r.ticker:<8} {r.score:<8} "
                f"{grade_icon + r.grade:<8} "
                f"{r.eps_growth*100:+.0f}%{'':<3} "
                f"{r.roe*100:.0f}%{'':<2} "
                f"{r.rs_value:+.0f}%{'':<2} "
                f"{r.sector[:25]}"
            )
    else:
        print("  Ninguna acción alcanzó el score mínimo de 22/32.")

    # ── 7. Guardar JSON ────────────────────────────────────────────────────
    _save_results(results, config)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  GUARDAR RESULTADOS
# ═══════════════════════════════════════════════════════════════════════════════

def _save_results(results: list, config: Config,
                  market_blocked: bool = False,
                  market_note: str = "") -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")

    passing = [r for r in results if r.passes_filter]
    all_res = [r for r in results if not r.error or r.score > 0]

    payload = {
        "generated_at":    datetime.utcnow().isoformat() + "Z",
        "date":            today,
        "market_blocked":  market_blocked,
        "market_note":     market_note,
        "total_scanned":   len(results),
        "total_passing":   len(passing),
        "results":         [r.to_dict() for r in passing],
        "all_results":     [r.to_dict() for r in all_res],
    }

    # results_latest.json (sobreescribe siempre)
    latest_path = Path(config.pipeline.output_latest)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n  Guardado → {latest_path}")

    # results_YYYY-MM-DD.json (historial)
    dated_path = Path(
        config.pipeline.output_dated.replace("{date}", today)
    )
    dated_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  Historial → {dated_path}")

    # watchlist TradingView
    if passing:
        wl_path = Path(config.pipeline.output_watchlist_tv)
        lines   = [
            f"### CANSLIM Scanner {today}",
            f"### {len(passing)} acciones · score >= 22/32",
            "",
        ]
        for r in passing:
            lines.append(f"### {r.ticker} | {r.grade.upper()} | Score {r.score}/32")
            lines.append(r.ticker)
        wl_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"  Watchlist TV → {wl_path}\n")


def _print_progress(done: int, total: int, res: ScanResult) -> None:
    bar_len = 25
    filled  = int(bar_len * done / total)
    bar     = "█" * filled + "░" * (bar_len - filled)
    if res.error and not res.weinstein_passed:
        status = "✗ error"
    elif not res.weinstein_passed:
        status = f"Stage {res.weinstein_stage}"
    else:
        status = f"✓ {res.score}/32"
    print(f"  [{bar}] {done:>3}/{total}  {res.ticker:<7} {status}   ",
          end="\r", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="CANSLIM Scanner + Weinstein Stage 2"
    )
    parser.add_argument("--tickers",  nargs="+", metavar="T",
                        help="Tickers específicos (ej: NVDA AAPL MSFT)")
    parser.add_argument("--universe", default="default",
                       choices=["default", "sp500", "nasdaq100", "sp500_nasdaq", "combined", "custom"],
                        help="Universo a escanear (default: default)")
    parser.add_argument("--source",   default="yfinance",
                        choices=["yfinance", "fmp"],
                        help="Fuente de datos")
    parser.add_argument("--workers",  type=int, default=8,
                        help="Hilos paralelos (default: 8)")
    parser.add_argument("--verbose",  action="store_true",
                        help="Logging detallado")
    args = parser.parse_args()

    config = Config()
    config.pipeline.data_source = args.source
    config.pipeline.workers     = args.workers

    run(config=config, tickers=args.tickers,
        universe=args.universe, verbose=args.verbose)


if __name__ == "__main__":
    main()
