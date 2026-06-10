"""
scorer.py — Agregador de score CANSLIM + Weinstein
====================================================
Recibe los resultados de todos los módulos y genera
el ScanResult final con score 0–32 y detalle por criterio.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("canslim.scorer")


@dataclass
class ScanResult:
    ticker:     str
    name:       str   = ""
    sector:     str   = ""
    industry:   str   = ""
    market_cap: float = 0.0
    scan_date:  str   = ""

    # Scores por criterio
    score_weinstein: int = 0
    score_m:         int = 0
    score_c:         int = 0
    score_a:         int = 0
    score_n:         int = 0
    score_s:         int = 0
    score_l:         int = 0
    score_i:         int = 0

    # Bloqueantes
    weinstein_passed: bool = False
    market_passed:    bool = False

    # Score total
    score:     int = 0
    max_score: int = 32

    # Detalle completo por criterio (para la app web)
    details: dict = field(default_factory=dict)

    # Valores clave para la tabla de la app
    eps_growth:      float = 0.0
    revenue_growth:  float = 0.0
    roe:             float = 0.0
    rs_value:        float = 0.0
    rs_percentile:   int   = 0
    buy_point:       float = 0.0
    vol_ratio:       float = 0.0
    inst_pct:        float = 0.0
    weinstein_stage: int   = 0

    # Estado del resultado
    error: str = ""

    @property
    def grade(self) -> str:
        """Etiqueta de calidad para la app web."""
        if self.score >= 30: return "elite"
        if self.score >= 27: return "strong"
        if self.score >= 22: return "valid"
        return "weak"

    @property
    def passes_filter(self) -> bool:
        return (self.weinstein_passed
                and self.market_passed
                and self.score >= 22)

    def to_dict(self) -> dict:
        """Serializa a dict para JSON."""
        return {
            "ticker":          self.ticker,
            "name":            self.name,
            "sector":          self.sector,
            "industry":        self.industry,
            "market_cap":      self.market_cap,
            "scan_date":       self.scan_date,
            "score":           self.score,
            "max_score":       self.max_score,
            "grade":           self.grade,
            "weinstein_stage": self.weinstein_stage,
            "scores": {
                "weinstein": self.score_weinstein,
                "M":         self.score_m,
                "C":         self.score_c,
                "A":         self.score_a,
                "N":         self.score_n,
                "S":         self.score_s,
                "L":         self.score_l,
                "I":         self.score_i,
            },
            "metrics": {
                "eps_growth":     round(self.eps_growth * 100, 1),
                "revenue_growth": round(self.revenue_growth * 100, 1),
                "roe":            round(self.roe * 100, 1),
                "rs_value":       self.rs_value,
                "rs_percentile":  self.rs_percentile,
                "buy_point":      self.buy_point,
                "vol_ratio":      self.vol_ratio,
                "inst_pct":       round(self.inst_pct * 100, 1),
            },
            "details": self.details,
            "error":   self.error,
        }


def build_result(
    ticker:        str,
    fund_data,
    weinstein_res,
    market_res,
    c_res,
    a_res,
    n_res,
    s_res,
    l_res,
    i_res,
    cfg,
) -> ScanResult:
    """
    Construye el ScanResult final combinando todos los resultados.
    Aplica reglas de bloqueo y calcula el score total.
    """
    scfg = cfg.scoring
    res  = ScanResult(
        ticker    = ticker,
        scan_date = datetime.utcnow().strftime("%Y-%m-%d"),
    )

    # Meta
    if fund_data:
        res.name       = fund_data.name
        res.sector     = fund_data.sector
        res.industry   = fund_data.industry
        res.market_cap = fund_data.market_cap

    # ── Bloqueantes ───────────────────────────────────────────────────────
    res.weinstein_passed = weinstein_res.passed if weinstein_res else False
    res.market_passed    = market_res.passed    if market_res    else False
    res.weinstein_stage  = weinstein_res.stage  if weinstein_res else 0

    # Si algún bloqueante falla → score 0, no seguir
    if not res.weinstein_passed or not res.market_passed:
        reason = []
        if not res.weinstein_passed:
            stage = weinstein_res.stage if weinstein_res else 0
            reason.append(f"Stage {stage} (no Stage 2)")
        if not res.market_passed:
            reason.append("Mercado bajista")
        res.error = " · ".join(reason)
        res.score_weinstein = weinstein_res.score if weinstein_res else 0
        res.score_m         = market_res.score    if market_res    else 0
        res.details = _build_details(weinstein_res, market_res, None,
                                     None, None, None, None, None)
        return res

    # ── Scores por criterio ───────────────────────────────────────────────
    res.score_weinstein = weinstein_res.score if weinstein_res else 0
    res.score_m         = market_res.score    if market_res    else 0
    res.score_c         = c_res.score         if c_res         else 0
    res.score_a         = a_res.score         if a_res         else 0
    res.score_n         = n_res.score         if n_res         else 0
    res.score_s         = s_res.score         if s_res         else 0
    res.score_l         = l_res.score         if l_res         else 0
    res.score_i         = i_res.score         if i_res         else 0

    # Score total — máximo 32
    # Weinstein(6) + M(5) + C(4) + A(4) + N(4) + S(4) + L(3) + I(3) = 33
    # Normalizamos a 32 (máximo del sistema)
    raw_score = (res.score_weinstein + res.score_m + res.score_c +
                 res.score_a + res.score_n + res.score_s +
                 res.score_l + res.score_i)
    res.score = min(raw_score, scfg.score_max)

    # ── Métricas clave para la app ────────────────────────────────────────
    if c_res:
        res.eps_growth     = c_res.eps_growth
        res.revenue_growth = c_res.revenue_growth
    if a_res:
        res.roe            = a_res.roe_latest
    if n_res:
        res.buy_point      = n_res.buy_point
        res.vol_ratio      = n_res.vol_ratio
    if l_res:
        res.rs_value       = l_res.rs_value
        res.rs_percentile  = l_res.rs_percentile
    if i_res:
        res.inst_pct       = i_res.inst_pct

    # ── Detalle completo ──────────────────────────────────────────────────
    res.details = _build_details(
        weinstein_res, market_res, c_res,
        a_res, n_res, s_res, l_res, i_res
    )

    return res


def _build_details(w, m, c, a, n, s, l, i) -> dict:
    """Construye el dict de detalles para JSON."""
    d = {}
    if w: d["weinstein"] = w.details
    if m: d["M"]         = m.details
    if c: d["C"]         = c.details
    if a: d["A"]         = a.details
    if n: d["N"]         = n.details
    if s: d["S"]         = s.details
    if l: d["L"]         = l.details
    if i: d["I"]         = i.details
    return d


# ── Integración mejoras v2 ────────────────────────────────────────────────────

def build_result_v2(
    ticker, fund_data, weinstein_res, market_res,
    c_res, a_res, n_res, s_res, l_res, i_res,
    sector_res, surprise_res, entry_params, cfg
) -> ScanResult:
    """
    Versión 2 del builder — incluye sector Stage 2,
    earnings surprise y parámetros de entrada.
    """
    from .criteria_entry import to_dict as entry_to_dict

    res = build_result(
        ticker, fund_data, weinstein_res, market_res,
        c_res, a_res, n_res, s_res, l_res, i_res, cfg
    )

    # Sector eliminatorio
    if sector_res and not sector_res.passed:
        res.score   = 0
        res.error   = f"Sector en Stage {sector_res.stage} ({sector_res.etf})"
        res.details["sector"] = {
            "passed": False,
            "note":   sector_res.note
        }
        return res

    if sector_res:
        res.details["sector"] = {
            "passed": sector_res.passed,
            "note":   sector_res.note
        }

    # Earnings surprise — modifica score de C
    if surprise_res and surprise_res.available:
        res.score = min(res.score + surprise_res.score_modifier,
                        cfg.scoring.score_max)
        res.score = max(res.score, 0)
        res.details["earnings_surprise"] = {
            "passed":       surprise_res.beat,
            "surprise_pct": surprise_res.surprise_pct,
            "modifier":     surprise_res.score_modifier,
            "note":         surprise_res.note
        }

    # Parámetros de entrada
    if entry_params:
        res.details["entry"] = entry_to_dict(entry_params)
        if entry_params.valid:
            res.details["entry"]["actionable"] = entry_params.actionable

    return res
