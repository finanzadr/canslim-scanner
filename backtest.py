"""
backtest.py — Validación histórica del scanner CANSLIM
=======================================================
Lee el historial de resultados en data/ y cruza cada ticker
con el precio real 4, 8 y 12 semanas después.

Pregunta clave: ¿Los tickers con score ≥26 superan al SPX?

Uso:
    python backtest.py                    # analiza todo el historial
    python backtest.py --min-score 22     # solo tickers con score >= 22
    python backtest.py --weeks 8          # horizonte de 8 semanas
    python backtest.py --output reporte.csv
"""

import argparse
import glob
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


# ═══════════════════════════════════════════════════════════════════════════════
#  CARGAR HISTORIAL
# ═══════════════════════════════════════════════════════════════════════════════

def load_history(data_dir: str = "data") -> list[dict]:
    """Carga todos los results_YYYY-MM-DD.json del directorio data/."""
    files = sorted(glob.glob(f"{data_dir}/results_20*.json"))

    if not files:
        print(f"  Sin archivos de historial en {data_dir}/")
        print(f"  El backtest necesita al menos 2 semanas de datos del scanner.")
        return []

    rows = []
    for f in files:
        try:
            date_str = Path(f).stem.replace("results_", "")
            data     = json.loads(Path(f).read_text(encoding="utf-8"))

            # Saltar si el mercado estaba bloqueado ese día
            if data.get("market_blocked"):
                continue

            for row in data.get("results", []):
                rows.append({
                    "ticker":     row["ticker"],
                    "name":       row.get("name", ""),
                    "sector":     row.get("sector", ""),
                    "score":      row.get("score", 0),
                    "grade":      row.get("grade", ""),
                    "eps_growth": row.get("metrics", {}).get("eps_growth", 0),
                    "roe":        row.get("metrics", {}).get("roe", 0),
                    "rs_value":   row.get("metrics", {}).get("rs_value", 0),
                    "scan_date":  date_str,
                })
        except Exception as exc:
            print(f"  Error leyendo {f}: {exc}")

    print(f"  Historial cargado: {len(rows)} registros de {len(files)} días")
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
#  CALCULAR RETORNOS
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_returns(rows: list[dict], weeks: int = 8) -> pd.DataFrame:
    """
    Para cada ticker + fecha, descarga precios y calcula retorno a N semanas.
    También descarga SPY para comparar.
    """
    tickers_needed = list(set(r["ticker"] for r in rows))
    tickers_needed.append("SPY")

    print(f"\n  Descargando precios para {len(tickers_needed)} tickers...")

    # Rango de fechas
    dates = [r["scan_date"] for r in rows]
    start = min(dates)
    end   = (datetime.now() + timedelta(weeks=weeks + 2)).strftime("%Y-%m-%d")

    # Descargar todo en batch (más rápido)
    try:
        prices = yf.download(
            tickers_needed,
            start=start,
            end=end,
            progress=False,
            auto_adjust=True,
        )["Close"]
    except Exception as exc:
        print(f"  Error descargando precios: {exc}")
        return pd.DataFrame()

    if isinstance(prices, pd.Series):
        prices = prices.to_frame()

    prices.index = pd.to_datetime(prices.index).tz_localize(None)

    results = []
    days    = weeks * 5

    for row in rows:
        ticker    = row["ticker"]
        scan_date = pd.Timestamp(row["scan_date"])

        if ticker not in prices.columns:
            continue

        # Precio en la fecha del scan (o el día hábil más cercano)
        future = prices[ticker].loc[scan_date:]
        spy_f  = prices["SPY"].loc[scan_date:] if "SPY" in prices.columns else None

        if len(future) < 2:
            continue

        entry_price = float(future.iloc[0])
        if entry_price == 0 or pd.isna(entry_price):
            continue

        # Retornos a 4, 8 y 12 semanas
        def ret_at(d):
            idx = min(d, len(future) - 1)
            p   = float(future.iloc[idx])
            return round((p / entry_price - 1) * 100, 2) if p and not pd.isna(p) else None

        def spy_ret_at(d):
            if spy_f is None or len(spy_f) < 2:
                return None
            idx = min(d, len(spy_f) - 1)
            ep  = float(spy_f.iloc[0])
            p   = float(spy_f.iloc[idx])
            return round((p / ep - 1) * 100, 2) if ep and p and not pd.isna(p) else None

        ret_4w  = ret_at(20)
        ret_8w  = ret_at(40)
        ret_12w = ret_at(60)
        spy_4w  = spy_ret_at(20)
        spy_8w  = spy_ret_at(40)
        spy_12w = spy_ret_at(60)

        results.append({
            **row,
            "entry_price": round(entry_price, 2),
            "ret_4w":      ret_4w,
            "ret_8w":      ret_8w,
            "ret_12w":     ret_12w,
            "spy_4w":      spy_4w,
            "spy_8w":      spy_8w,
            "spy_12w":     spy_12w,
            "alpha_4w":    round(ret_4w - spy_4w, 2) if ret_4w and spy_4w else None,
            "alpha_8w":    round(ret_8w - spy_8w, 2) if ret_8w and spy_8w else None,
            "alpha_12w":   round(ret_12w - spy_12w, 2) if ret_12w and spy_12w else None,
        })

    print(f"  Retornos calculados: {len(results)} registros válidos")
    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════════════════════
#  ANÁLISIS Y REPORTE
# ═══════════════════════════════════════════════════════════════════════════════

def analyze(df: pd.DataFrame) -> None:
    if df.empty:
        print("\n  Sin datos suficientes para analizar.")
        return

    print("\n" + "═" * 64)
    print("  BACKTEST CANSLIM Scanner — Análisis de rendimiento")
    print("═" * 64)

    # Filtrar filas con retorno a 8w disponible
    df8 = df.dropna(subset=["ret_8w", "alpha_8w"])
    if df8.empty:
        print("\n  Sin datos de retorno a 8 semanas aún.")
        print("  El backtest necesita que pasen 8 semanas desde los primeros scans.")
        return

    print(f"\n  Período analizado: {df8['scan_date'].min()} → {df8['scan_date'].max()}")
    print(f"  Trades analizados: {len(df8)}")
    print(f"  Tickers únicos:    {df8['ticker'].nunique()}")

    # ── Por banda de score ────────────────────────────────────────────────
    print("\n  Retorno promedio a 8 semanas por banda de score:")
    print(f"  {'Score':<14} {'N':<6} {'Ret 8w':<10} {'Alpha vs SPX':<14} {'Win Rate'}")
    print("  " + "─" * 56)

    bins   = [0, 20, 22, 24, 26, 28, 30, 32]
    labels = ["<20", "20-22", "22-24", "24-26", "26-28", "28-30", "30-32"]
    df8["score_band"] = pd.cut(df8["score"], bins=bins, labels=labels, right=True)

    for band in labels:
        sub = df8[df8["score_band"] == band]
        if len(sub) == 0:
            continue
        avg_ret   = sub["ret_8w"].mean()
        avg_alpha = sub["alpha_8w"].mean()
        win_rate  = (sub["ret_8w"] > 0).mean() * 100
        beat_spx  = (sub["alpha_8w"] > 0).mean() * 100
        col       = "✓" if avg_ret > 0 and avg_alpha > 0 else "✗"
        print(f"  {band:<14} {len(sub):<6} {avg_ret:+.1f}%{'':<4} "
              f"Alpha {avg_alpha:+.1f}%{'':<4} "
              f"Win {win_rate:.0f}% Beat {beat_spx:.0f}% {col}")

    # ── Top 10 mejores ────────────────────────────────────────────────────
    print(f"\n  Top 10 setups por alpha a 8 semanas:")
    print(f"  {'Ticker':<8} {'Fecha':<12} {'Score':<7} {'Ret 8w':<10} {'Alpha'}")
    print("  " + "─" * 48)
    top = df8.nlargest(10, "alpha_8w")[
        ["ticker", "scan_date", "score", "ret_8w", "alpha_8w"]
    ]
    for _, r in top.iterrows():
        print(f"  {r['ticker']:<8} {r['scan_date']:<12} {r['score']:<7} "
              f"{r['ret_8w']:+.1f}%{'':<4} {r['alpha_8w']:+.1f}%")

    # ── Veredicto ─────────────────────────────────────────────────────────
    high_score  = df8[df8["score"] >= 26]
    avg_hs      = high_score["ret_8w"].mean() if len(high_score) > 0 else None
    avg_alpha_hs = high_score["alpha_8w"].mean() if len(high_score) > 0 else None

    print(f"\n  {'═'*56}")
    print(f"  VEREDICTO — Score ≥ 26:")
    if avg_hs is not None and len(high_score) >= 3:
        verdict = "✓ SISTEMA VÁLIDO" if avg_alpha_hs and avg_alpha_hs > 2 else "⚠ REVISAR CRITERIOS"
        print(f"  {verdict}")
        print(f"  Retorno promedio 8 semanas: {avg_hs:+.1f}%")
        print(f"  Alpha vs SPX:               {avg_alpha_hs:+.1f}%")
        print(f"  N trades analizados:        {len(high_score)}")
    else:
        print(f"  Datos insuficientes (< 3 trades con score ≥ 26)")
        print(f"  Necesitas más historial — el scanner lleva poco tiempo corriendo.")
    print(f"  {'═'*56}\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Backtest CANSLIM Scanner")
    parser.add_argument("--data-dir",  default="data",     help="Carpeta con historial JSON")
    parser.add_argument("--min-score", type=int, default=0, help="Score mínimo a incluir")
    parser.add_argument("--weeks",     type=int, default=8,  help="Horizonte de retorno en semanas")
    parser.add_argument("--output",    metavar="FILE",       help="Exportar CSV (ej: backtest.csv)")
    args = parser.parse_args()

    rows = load_history(args.data_dir)
    if not rows:
        sys.exit(0)

    if args.min_score:
        rows = [r for r in rows if r["score"] >= args.min_score]
        print(f"  Filtrado a score >= {args.min_score}: {len(rows)} registros")

    df = fetch_returns(rows, weeks=args.weeks)
    analyze(df)

    if args.output and not df.empty:
        df.to_csv(args.output, index=False)
        print(f"  CSV exportado → {args.output}")


if __name__ == "__main__":
    main()
