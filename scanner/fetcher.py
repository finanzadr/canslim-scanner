"""
fetcher.py — Capa de datos
===========================
Abstrae Yahoo Finance (gratis) y FMP (premium).
Ambos backends devuelven los mismos objetos para que
el resto del pipeline no sepa ni le importe qué fuente usa.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger("canslim.fetcher")


# ══════════════════════════════════════════════════════════════════════════════
#  OBJETOS DE DATOS — lo que devuelve el fetcher
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PriceData:
    """Serie de precios diarios y semanales."""
    ticker:       str
    daily:        Optional[pd.DataFrame] = None   # OHLCV diario
    weekly:       Optional[pd.DataFrame] = None   # OHLCV semanal
    error:        str = ""


@dataclass
class FundamentalData:
    """Datos fundamentales trimestrales y anuales."""
    ticker:       str

    # Criterio C — trimestral (más reciente primero)
    quarterly_eps:          list[float] = field(default_factory=list)
    quarterly_revenue:      list[float] = field(default_factory=list)
    quarterly_eps_yoy:      list[float] = field(default_factory=list)
    quarterly_revenue_yoy:  list[float] = field(default_factory=list)
    quarterly_eps_estimate: list[float] = field(default_factory=list)  # para earnings beat

    # Criterio A — anual (más reciente primero)
    annual_eps:             list[float] = field(default_factory=list)
    annual_roe:             list[float] = field(default_factory=list)
    annual_net_margin:      list[float] = field(default_factory=list)
    annual_shares:          list[float] = field(default_factory=list)  # para recompras (S)

    # Criterio I — institucional
    institutional_pct:      float = 0.0
    institutional_pct_prev: float = 0.0   # trimestre anterior

    # Meta
    name:       str = ""
    sector:     str = ""
    industry:   str = ""
    market_cap: float = 0.0
    float_shares: float = 0.0             # flotación (S)
    error:      str = ""

    # Earnings date
    next_earnings_date: str = ""          # "2026-07-23" o ""
    days_to_earnings:   int = -1          # días hasta earnings (-1 = desconocido)
    earnings_warning:   bool = False      # True si earnings en <= 14 días


@dataclass
class MarketData:
    """Datos de índices para el criterio M."""
    spx:    Optional[pd.DataFrame] = None
    nasdaq: Optional[pd.DataFrame] = None
    error:  str = ""


# ══════════════════════════════════════════════════════════════════════════════
#  YAHOO FINANCE FETCHER
# ══════════════════════════════════════════════════════════════════════════════

class YFinanceFetcher:
    def __init__(self, cfg):
        self.cfg = cfg.pipeline
        self.wcfg = cfg.weinstein

    # ── Precios ───────────────────────────────────────────────────────────────

    def fetch_prices(self, ticker: str) -> PriceData:
        data = PriceData(ticker=ticker)
        for attempt in range(self.cfg.retry_attempts + 1):
            try:
                tk = yf.Ticker(ticker)
                # 2 años de datos diarios para MA200, bases, volumen
                daily = tk.history(period="2y", interval="1d", auto_adjust=True)
                if daily.empty:
                    data.error = "Sin datos de precio"
                    return data
                daily.index = pd.to_datetime(daily.index).tz_localize(None)
                data.daily = daily

                # Semanal para Weinstein MA30/MA40
                weekly = tk.history(period="2y", interval="1wk", auto_adjust=True)
                if not weekly.empty:
                    weekly.index = pd.to_datetime(weekly.index).tz_localize(None)
                    data.weekly = weekly

                return data

            except Exception as exc:
                if attempt < self.cfg.retry_attempts:
                    time.sleep(self.cfg.retry_delay * (attempt + 1))
                else:
                    data.error = str(exc)
                    logger.debug(f"{ticker} prices: {exc}")
        return data

    # ── Fundamentales ─────────────────────────────────────────────────────────

    def fetch_fundamentals(self, ticker: str) -> FundamentalData:
        data = FundamentalData(ticker=ticker)
        for attempt in range(self.cfg.retry_attempts + 1):
            try:
                tk   = yf.Ticker(ticker)
                info = tk.info or {}

                data.name        = info.get("longName", ticker)
                data.sector      = info.get("sector", "")
                data.industry    = info.get("industry", "")
                data.market_cap  = float(info.get("marketCap", 0) or 0)
                data.float_shares = float(info.get("floatShares", 0) or 0)
                data.institutional_pct = float(
                    info.get("heldPercentInstitutions", 0) or 0
                )

                # ── Trimestral ────────────────────────────────────────────
                qinc = tk.quarterly_income_stmt
                if qinc is not None and not qinc.empty:
                    eps_vals = _extract_row(qinc, ["diluted eps", "basic eps"])
                    rev_vals = _extract_row(qinc, ["total revenue", "totalrevenue"])

                    if eps_vals:
                        data.quarterly_eps     = eps_vals
                        data.quarterly_eps_yoy = _yoy_growth(eps_vals)
                    if rev_vals:
                        data.quarterly_revenue     = rev_vals
                        data.quarterly_revenue_yoy = _yoy_growth(rev_vals)

                # ── Anual ─────────────────────────────────────────────────
                ainc = tk.income_stmt
                abal = tk.balance_sheet

                if ainc is not None and not ainc.empty:
                    eps_a  = _extract_row(ainc, ["diluted eps", "basic eps"])
                    net_i  = _extract_row(ainc, ["net income", "netincome"])
                    tot_r  = _extract_row(ainc, ["total revenue", "totalrevenue"])
                    shs    = _extract_row(ainc, ["diluted average shares",
                                                  "basic average shares"])

                    if eps_a:
                        data.annual_eps = eps_a
                    if net_i and tot_r:
                        data.annual_net_margin = [
                            ni / rv if rv and rv != 0 else 0.0
                            for ni, rv in zip(net_i, tot_r)
                        ]
                    if shs:
                        data.annual_shares = shs

                # ROE
                if ainc is not None and abal is not None \
                        and not ainc.empty and not abal.empty:
                    net_i  = _extract_row(ainc, ["net income", "netincome"])
                    equity = _extract_row(abal, [
                        "stockholders equity", "totalstockholderequity",
                        "total equity", "common stock equity"
                    ])
                    if net_i and equity:
                        data.annual_roe = [
                            ni / eq if eq and eq != 0 else 0.0
                            for ni, eq in zip(net_i, equity)
                        ]

                # ── Próximos earnings ─────────────────────────────────────
                _fetch_earnings_date(tk, info, data)

                return data

            except Exception as exc:
                if attempt < self.cfg.retry_attempts:
                    time.sleep(self.cfg.retry_delay * (attempt + 1))
                else:
                    data.error = str(exc)
                    logger.debug(f"{ticker} fundamentals: {exc}")
        return data

    # ── Mercado ───────────────────────────────────────────────────────────────

    def fetch_market(self, spx_ticker: str, nasdaq_ticker: str) -> MarketData:
        mkt = MarketData()
        try:
            spx = yf.Ticker(spx_ticker).history(period="1y", interval="1d",
                                                  auto_adjust=True)
            if not spx.empty:
                spx.index = pd.to_datetime(spx.index).tz_localize(None)
                mkt.spx = spx

            qqq = yf.Ticker(nasdaq_ticker).history(period="1y", interval="1d",
                                                     auto_adjust=True)
            if not qqq.empty:
                qqq.index = pd.to_datetime(qqq.index).tz_localize(None)
                mkt.nasdaq = qqq

        except Exception as exc:
            mkt.error = str(exc)
            logger.error(f"fetch_market: {exc}")
        return mkt


# ══════════════════════════════════════════════════════════════════════════════
#  FMP FETCHER
# ══════════════════════════════════════════════════════════════════════════════

class FMPFetcher:
    """
    Financial Modeling Prep — datos más limpios y con earnings estimates.
    Requiere FMP_API_KEY en .env. Plan gratuito: 250 req/día.
    """
    def __init__(self, cfg):
        self.cfg     = cfg.pipeline
        self.api_key = cfg.pipeline.fmp_api_key
        self.base    = "https://financialmodelingprep.com/api/v3"
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "CANSLIM-Scanner/2.0"

    def _get(self, path: str, params: dict = None) -> list | dict | None:
        url    = f"{self.base}/{path}"
        params = {**(params or {}), "apikey": self.api_key}
        for attempt in range(self.cfg.retry_attempts + 1):
            try:
                r = self.session.get(url, params=params,
                                     timeout=self.cfg.request_timeout)
                r.raise_for_status()
                return r.json()
            except Exception as exc:
                if attempt < self.cfg.retry_attempts:
                    time.sleep(self.cfg.retry_delay * (attempt + 1))
                else:
                    logger.debug(f"FMP {path}: {exc}")
                    return None

    def fetch_prices(self, ticker: str) -> PriceData:
        """FMP precio — usa yfinance como fallback para no gastar requests."""
        yf_fetcher = YFinanceFetcher.__new__(YFinanceFetcher)
        yf_fetcher.cfg  = self.cfg
        yf_fetcher.wcfg = None
        return yf_fetcher.fetch_prices(ticker)

    def fetch_fundamentals(self, ticker: str) -> FundamentalData:
        data = FundamentalData(ticker=ticker)

        # Perfil
        profile = self._get(f"profile/{ticker}")
        if profile and isinstance(profile, list) and profile:
            p = profile[0]
            data.name        = p.get("companyName", ticker)
            data.sector      = p.get("sector", "")
            data.industry    = p.get("industry", "")
            data.market_cap  = float(p.get("mktCap", 0) or 0)

        # Trimestral
        q_inc = self._get(f"income-statement/{ticker}",
                          {"period": "quarter", "limit": 9})
        if q_inc and isinstance(q_inc, list):
            eps_l = [float(r.get("eps") or 0) for r in q_inc]
            rev_l = [float(r.get("revenue") or 0) for r in q_inc]
            data.quarterly_eps          = eps_l
            data.quarterly_revenue      = rev_l
            data.quarterly_eps_yoy      = _yoy_growth(eps_l)
            data.quarterly_revenue_yoy  = _yoy_growth(rev_l)

        # Earnings estimates (solo FMP)
        est = self._get(f"analyst-estimates/{ticker}", {"limit": 4})
        if est and isinstance(est, list):
            data.quarterly_eps_estimate = [
                float(r.get("estimatedEpsAvg") or 0) for r in est
            ]

        # Anual
        a_inc = self._get(f"income-statement/{ticker}",
                          {"period": "annual", "limit": 5})
        if a_inc and isinstance(a_inc, list):
            data.annual_eps = [float(r.get("eps") or 0) for r in a_inc]
            net_i = [float(r.get("netIncome") or 0) for r in a_inc]
            rev_a = [float(r.get("revenue") or 1) for r in a_inc]
            data.annual_net_margin = [
                ni / rv for ni, rv in zip(net_i, rev_a)
            ]
            data.annual_shares = [
                float(r.get("weightedAverageShsOutDil") or 0) for r in a_inc
            ]

        # ROE
        ratios = self._get(f"ratios/{ticker}", {"limit": 5})
        if ratios and isinstance(ratios, list):
            data.annual_roe = [float(r.get("returnOnEquity") or 0)
                               for r in ratios]

        # Institucional
        inst = self._get(f"institutional-holder/{ticker}")
        if inst and isinstance(inst, list):
            total_held = sum(float(r.get("shares", 0) or 0) for r in inst)
            if data.float_shares and data.float_shares > 0:
                data.institutional_pct = min(total_held / data.float_shares, 1.0)

        return data

    def fetch_market(self, spx_ticker: str, nasdaq_ticker: str) -> MarketData:
        yf_fetcher = YFinanceFetcher.__new__(YFinanceFetcher)
        yf_fetcher.cfg  = self.cfg
        yf_fetcher.wcfg = None
        return yf_fetcher.fetch_market(spx_ticker, nasdaq_ticker)


# ══════════════════════════════════════════════════════════════════════════════
#  FACTORY
# ══════════════════════════════════════════════════════════════════════════════

def get_fetcher(cfg):
    if cfg.pipeline.data_source == "fmp":
        return FMPFetcher(cfg)
    return YFinanceFetcher(cfg)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _extract_row(df: pd.DataFrame, candidates: list[str]) -> list[float]:
    """Extrae una fila de un DataFrame por nombre parcial."""
    for row_name in df.index:
        rn = str(row_name).lower().replace(" ", "").replace("_", "")
        for cand in candidates:
            c = cand.lower().replace(" ", "").replace("_", "")
            if c in rn:
                vals = []
                for v in df.loc[row_name].values:
                    try:
                        f = float(v)
                        if not pd.isna(f):
                            vals.append(f)
                    except (TypeError, ValueError):
                        pass
                if vals:
                    return vals
    return []


def _yoy_growth(values: list[float]) -> list[float]:
    """
    Crecimiento YoY trimestral.
    values[0] = más reciente. Compara posición 0 vs 4, 1 vs 5, etc.
    """
    growths = []
    for i in range(len(values) - 4):
        curr     = values[i]
        year_ago = values[i + 4]
        if year_ago and year_ago != 0:
            g = (curr - year_ago) / abs(year_ago)
        else:
            g = 0.0
        growths.append(round(g, 4))
    return growths


def _fetch_earnings_date(tk, info: dict, data) -> None:
    """
    Obtiene la fecha del próximo earnings report desde yfinance.
    Actualiza data.next_earnings_date, data.days_to_earnings
    y data.earnings_warning (True si earnings en <= 14 días).

    Fuentes en orden de prioridad:
      1. info["earningsTimestamp"] o info["earningsDate"]
      2. tk.calendar (DataFrame con fechas)
      3. tk.earnings_dates (historial + próximas fechas)
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)

    # ── Fuente 1: info dict ───────────────────────────────────────────────
    for key in ("earningsTimestamp", "earningsTimestampStart",
                "earningsTimestampEnd"):
        ts = info.get(key)
        if ts and isinstance(ts, (int, float)) and ts > 0:
            try:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                if dt > now:
                    _set_earnings(data, dt, now)
                    return
            except Exception:
                pass

    # ── Fuente 2: calendar ────────────────────────────────────────────────
    try:
        cal = tk.calendar
        if cal is not None:
            # Puede ser dict o DataFrame según versión de yfinance
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    dates = ed if isinstance(ed, list) else [ed]
                    for d in dates:
                        try:
                            dt = pd.Timestamp(d).to_pydatetime()
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            if dt > now:
                                _set_earnings(data, dt, now)
                                return
                        except Exception:
                            pass
            elif hasattr(cal, "loc"):
                for row_name in cal.index:
                    if "earnings" in str(row_name).lower():
                        val = cal.loc[row_name]
                        vals = val.tolist() if hasattr(val, "tolist") else [val]
                        for v in vals:
                            try:
                                dt = pd.Timestamp(v).to_pydatetime()
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                if dt > now:
                                    _set_earnings(data, dt, now)
                                    return
                            except Exception:
                                pass
    except Exception:
        pass

    # ── Fuente 3: earnings_dates ──────────────────────────────────────────
    try:
        ed = tk.earnings_dates
        if ed is not None and not ed.empty:
            future = ed[ed.index > pd.Timestamp(now)]
            if not future.empty:
                next_dt = future.index[-1]   # más próximo
                dt = pd.Timestamp(next_dt).to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                _set_earnings(data, dt, now)
    except Exception:
        pass


def _set_earnings(data, dt, now) -> None:
    """Asigna los campos de earnings en FundamentalData."""
    from datetime import timezone
    data.next_earnings_date = dt.strftime("%Y-%m-%d")
    delta = (dt.replace(tzinfo=timezone.utc)
             if dt.tzinfo is None else dt) - now
    data.days_to_earnings  = max(0, delta.days)
    data.earnings_warning  = data.days_to_earnings <= 14
