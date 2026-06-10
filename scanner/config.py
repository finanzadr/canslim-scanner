"""
CANSLIM Scanner — Configuración central
========================================
Todos los umbrales, pesos y parámetros del sistema en un solo lugar.
Edita aquí para afinar el scanner sin tocar lógica de negocio.

Sistema de score:
  - Score máximo : 32 puntos
  - Bloqueantes  : Weinstein Stage 2 y criterio M (mercado)
                   Si cualquiera falla → acción/sesión descartada
  - Umbral app   : score >= 22 para aparecer en el dashboard
"""

from dataclasses import dataclass, field
from dotenv import load_dotenv
import os

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
#  WEINSTEIN STAGE 2  — portero #1 (bloqueante)
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class WeinsteinConfig:
    # Medias móviles semanales (Weinstein usa MA30 semanal, no MA50 diaria)
    ma_primary_weeks:   int   = 30       # MA principal — debe ser ascendente
    ma_secondary_weeks: int   = 40       # MA secundaria — primaria debe estar sobre esta
    ma_slope_lookback:  int   = 4        # semanas atrás para medir pendiente de MA30

    # Condiciones de precio
    price_above_ma:     bool  = True     # precio de cierre > MA30 semanal
    ma_primary_rising:  bool  = True     # MA30[0] > MA30[slope_lookback]
    ma_cross_required:  bool  = True     # MA30 > MA40

    # Confirmación diaria adicional
    price_above_ma200_daily: bool = True # cierre diario > MA200

    # Volumen — patrón de acumulación
    vol_ratio_weeks:    int   = 10       # semanas para medir ratio vol alcista/bajista
    vol_ratio_min:      float = 1.2      # vol en alzas / vol en bajas > este valor

    # Stage 4 (declive) — descalifica inmediatamente
    reject_stage4:      bool  = True     # precio < MA30 descendente = Stage 4


# ══════════════════════════════════════════════════════════════════════════════
#  M — MARKET DIRECTION  — portero #2 (bloqueante de sesión completa)
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class MarketConfig:
    # Índices a monitorear
    spx_ticker:     str = "SPY"          # S&P 500 ETF
    nasdaq_ticker:  str = "QQQ"          # Nasdaq 100 ETF

    # Medias móviles del índice
    ma_short:       int = 50             # MA50 diario
    ma_long:        int = 200            # MA200 diario

    # Días de distribución (presión vendedora institucional)
    distribution_window:  int = 25       # sesiones a revisar
    distribution_max:     int = 6        # máximo días de distribución permitidos
    distribution_vol_min: float = 1.03   # vol día distrib. >= 1.03× día anterior

    # Follow-Through Day (FTD) — confirmación de rally
    ftd_required:        bool  = True    # exigir FTD para mercado alcista
    ftd_window_start:    int   = 4       # día mínimo del intento de rally
    ftd_window_end:      int   = 7       # día máximo del intento de rally
    ftd_gain_min:        float = 0.017   # ganancia mínima en FTD (1.7%)

    # Score máximo que aporta M al total
    max_score: int = 5


# ══════════════════════════════════════════════════════════════════════════════
#  C — CURRENT QUARTERLY EARNINGS
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class CriteriaC:
    # EPS trimestral YoY
    eps_growth_min:         float = 0.25   # +25% mínimo vs mismo trim año anterior
    eps_growth_ideal:       float = 0.40   # +40% = score completo en este sub-criterio

    # Ventas trimestrales YoY
    revenue_growth_min:     float = 0.25   # +25% mínimo
    revenue_growth_ideal:   float = 0.35   # +35% = score completo

    # Aceleración del EPS
    require_acceleration:   bool  = True   # último trim debe crecer más que el anterior
    acceleration_quarters:  int   = 3      # cuántos trimestres comparar

    # Earnings surprise (beat de estimados)
    require_beat:           bool  = True   # EPS actual > EPS estimado de analistas
    beat_margin_min:        float = 0.01   # al menos 1% sobre estimado

    # Datos
    quarters_required:      int   = 5      # mínimo trimestres necesarios (4 YoY + 1 accel)

    # Score máximo que aporta C al total
    max_score: int = 4


# ══════════════════════════════════════════════════════════════════════════════
#  A — ANNUAL EARNINGS GROWTH
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class CriteriaA:
    # EPS anual consecutivo
    eps_annual_growth_min:  float = 0.25   # +25% cada año
    eps_annual_growth_ideal:float = 0.35   # +35% = score completo
    years_required:         int   = 3      # años consecutivos de crecimiento

    # ROE
    roe_min:                float = 0.17   # 17% — umbral O'Neil
    roe_ideal:              float = 0.25   # 25% = score completo

    # Margen neto
    net_margin_min:         float = 0.05   # 5% mínimo
    net_margin_stable:      bool  = True   # no se comprime año a año

    # Descalificadores absolutos
    reject_any_negative_eps: bool = True   # cualquier año con EPS < 0 = fuera
    reject_declining_eps:    bool = True   # si EPS anual cayó en algún año = fuera

    # Score máximo que aporta A al total
    max_score: int = 4


# ══════════════════════════════════════════════════════════════════════════════
#  N — NEW HIGH / BREAKOUT / CATALYST
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class CriteriaN:
    # Zona de nuevo máximo
    high_52w_proximity:     float = 0.95   # precio >= 95% del máximo 52 semanas
    new_52w_high_bonus:     bool  = True   # bono si está en nuevo máximo absoluto

    # Ruptura de base
    breakout_vol_mult:      float = 1.40   # volumen >= 1.4× MA50 en la barra de ruptura
    breakout_vol_mult_ideal:float = 1.75   # >= 1.75× = score completo
    breakout_bullish_bar:   bool  = True   # cierre > apertura en barra de ruptura

    # Detección de base válida
    base_min_bars:          int   = 25     # mínimo de barras diarias
    base_max_bars:          int   = 65     # máximo de barras diarias
    base_depth_min:         float = 0.10   # corrección mínima desde techo (10%)
    base_depth_max:         float = 0.33   # corrección máxima (33%) — más = base fallida

    # Buy point y extensión
    pivot_buffer:           float = 0.02   # buy point = pivot high + 2%
    max_extension:          float = 0.05   # acción NO extendida > 5% del buy point

    # Score máximo que aporta N al total
    max_score: int = 4


# ══════════════════════════════════════════════════════════════════════════════
#  S — SUPPLY & DEMAND
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class CriteriaS:
    # Días de acumulación vs distribución
    acc_dist_weeks:         int   = 13     # ventana de 13 semanas
    acc_dist_ratio_min:     float = 1.0    # días acum > días distrib (ratio > 1)
    acc_dist_ratio_ideal:   float = 1.5    # ratio >= 1.5 = score completo

    # Ratio volumen alcista / bajista
    upvol_downvol_sessions: int   = 50     # últimas 50 sesiones
    upvol_downvol_min:      float = 1.2    # up-vol / down-vol > 1.2
    upvol_downvol_ideal:    float = 1.6    # >= 1.6 = score completo

    # Flotación (shares outstanding)
    float_max_shares:       float = 100e6  # 100 millones — flotación grande reduce volatilidad
    float_small_bonus:      float = 30e6   # < 30M = bono adicional

    # Recompras de acciones
    buyback_positive:       bool  = True   # shares outstanding cayendo YoY = positivo

    # Score máximo que aporta S al total
    max_score: int = 4


# ══════════════════════════════════════════════════════════════════════════════
#  L — LEADER OR LAGGARD
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class CriteriaL:
    # RS casero vs S&P500 (rendimiento relativo 12 meses)
    rs_period_days:         int   = 252    # 12 meses de trading
    rs_percentile_min:      int   = 80     # top 20% del universo escaneado
    rs_percentile_ideal:    int   = 90     # top 10% = score completo

    # Tendencia de la línea RS
    rs_trend_weeks:         int   = 8      # RS debe subir en últimas 8 semanas
    rs_trending_up:         bool  = True   # RS[0] > RS[rs_trend_weeks]

    # Sector también en Stage 2
    sector_etfs: dict = field(default_factory=lambda: {
        "Technology":            "XLK",
        "Health Care":           "XLV",
        "Consumer Discretionary":"XLY",
        "Industrials":           "XLI",
        "Financials":            "XLF",
        "Energy":                "XLE",
        "Materials":             "XLB",
        "Communication Services":"XLC",
        "Consumer Staples":      "XLP",
        "Utilities":             "XLU",
        "Real Estate":           "XLRE",
    })
    require_sector_stage2:  bool  = True   # sector ETF también sobre MA30 semanal

    # Score máximo que aporta L al total
    max_score: int = 3


# ══════════════════════════════════════════════════════════════════════════════
#  I — INSTITUTIONAL SPONSORSHIP
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class CriteriaI:
    # Porcentaje de acciones en manos institucionales
    inst_pct_min:           float = 0.30   # < 30% = sin interés institucional
    inst_pct_max:           float = 0.80   # > 80% = sobre-tenida, poco upside
    inst_pct_ideal_low:     float = 0.45   # zona ideal entre 45%–70%
    inst_pct_ideal_high:    float = 0.70

    # Tendencia del % institucional (creciente = acumulación)
    inst_trend_positive:    bool  = True   # debe estar subiendo
    inst_trend_quarters:    int   = 2      # comparar últimos 2 trimestres

    # Concentración en un solo fondo
    single_fund_max:        float = 0.20   # si 1 fondo tiene > 20% del float = riesgo

    # Score máximo que aporta I al total
    max_score: int = 3


# ══════════════════════════════════════════════════════════════════════════════
#  SCORING GLOBAL
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class ScoringConfig:
    # Umbrales de score total (máximo = 32)
    score_max:              int   = 32
    score_show_in_app:      int   = 22     # >= 22 aparece en el dashboard
    score_strong_setup:     int   = 27     # >= 27 = setup fuerte (resaltado en verde)
    score_elite_setup:      int   = 30     # >= 30 = setup élite (badge especial)

    # Criterios bloqueantes — si fallan, score = 0 sin importar el resto
    # (Weinstein Stage 2 y criterio M se manejan antes del loop de scoring)
    blocking_criteria: list = field(default_factory=lambda: ["weinstein", "M"])


# ══════════════════════════════════════════════════════════════════════════════
#  PIPELINE Y DATOS
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class PipelineConfig:
    # Fuente de datos
    data_source:            str   = "yfinance"   # "yfinance" | "fmp"
    fmp_api_key:            str   = field(default_factory=lambda: os.getenv("FMP_API_KEY", ""))

    # Paralelismo
    workers:                int   = 8
    request_timeout:        int   = 20
    retry_attempts:         int   = 2
    retry_delay:            float = 1.5

    # Horario (GitHub Actions corre en UTC)
    # 21:15 UTC = 5:15pm ET (mercado cierra 4pm ET)
    cron_utc:               str   = "15 21 * * 1-5"

    # Outputs
    output_latest:          str   = "data/results_latest.json"
    output_dated:           str   = "data/results_{date}.json"
    output_watchlist_tv:    str   = "data/watchlist_tv.txt"

    # Historial máximo de archivos JSON a mantener en el repo
    history_max_files:      int   = 30


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN MAESTRA — punto de entrada único
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class Config:
    weinstein:  WeinsteinConfig = field(default_factory=WeinsteinConfig)
    market:     MarketConfig    = field(default_factory=MarketConfig)
    c:          CriteriaC       = field(default_factory=CriteriaC)
    a:          CriteriaA       = field(default_factory=CriteriaA)
    n:          CriteriaN       = field(default_factory=CriteriaN)
    s:          CriteriaS       = field(default_factory=CriteriaS)
    l:          CriteriaL       = field(default_factory=CriteriaL)
    i:          CriteriaI       = field(default_factory=CriteriaI)
    scoring:    ScoringConfig   = field(default_factory=ScoringConfig)
    pipeline:   PipelineConfig  = field(default_factory=PipelineConfig)

    def __post_init__(self):
        if self.pipeline.data_source == "fmp" and not self.pipeline.fmp_api_key:
            raise ValueError(
                "FMP_API_KEY no encontrado.\n"
                "Copia .env.example a .env y agrega tu clave:\n"
                "  FMP_API_KEY=tu_clave_aqui\n"
                "Clave gratis en: https://financialmodelingprep.com"
            )


# Instancia global — importar desde cualquier módulo con:
#   from scanner.config import cfg
cfg = Config()
