# CANSLIM Scanner + Weinstein Stage 2

Scanner automático de acciones que combina la metodología CANSLIM de William O'Neil con el análisis de etapas de Stan Weinstein. Corre cada día de lunes a viernes vía GitHub Actions y publica los resultados en una app web a través de GitHub Pages.

---

## Qué hace

1. Verifica la dirección del mercado (criterio M) — si el mercado no está alcista, no procesa nada
2. Para cada acción del universo, verifica Weinstein Stage 2 — si no está en avance, la descarta
3. Evalúa los 6 criterios CANSLIM (C, A, N, S, L, I) con 32 sub-criterios en total
4. Genera un score de 0–32 y publica las acciones con score ≥ 22 en la app web

## Sistema de score

| Criterio | Sub-criterios | Peso |
|---|---|---|
| Weinstein Stage 2 | 6 | Bloqueante |
| M — Mercado | 5 | Bloqueante de sesión |
| C — EPS trimestral | 4 | Alto |
| A — EPS anual | 4 | Alto |
| N — Ruptura / nuevo máximo | 4 | Alto |
| S — Supply & demand | 4 | Medio |
| L — Relative Strength | 3 | Alto |
| I — Institucional | 3 | Medio |
| **Total** | **32** | |

**Umbrales de la app:**
- Score ≥ 22 → aparece en el dashboard
- Score ≥ 27 → setup fuerte (verde)
- Score ≥ 30 → setup élite (badge especial)

## Estructura del proyecto

```
canslim-scanner/
├── .github/workflows/
│   └── scanner.yml          # cron automático 5:15pm ET lun–vie
├── scanner/
│   ├── config.py            # todos los umbrales CANSLIM + Weinstein
│   ├── universe.py          # universos de tickers
│   ├── fetcher.py           # Yahoo Finance / FMP
│   ├── weinstein.py         # detector Stage 2
│   ├── criteria_c.py        # EPS trimestral
│   ├── criteria_a.py        # EPS anual + ROE
│   ├── criteria_n.py        # ruptura + base
│   ├── criteria_s.py        # supply & demand
│   ├── criteria_l.py        # RS casero vs SPX
│   ├── criteria_i.py        # institucional
│   ├── criteria_m.py        # dirección del mercado
│   ├── scorer.py            # agrega score 0–32
│   └── runner.py            # orquestador del pipeline
├── web/
│   ├── index.html           # dashboard
│   ├── app.js               # lógica de la app
│   └── style.css            # estilos
├── data/
│   ├── results_latest.json  # resultado del día (sobreescrito)
│   └── results_YYYY-MM-DD.json  # historial
├── requirements.txt
├── .env.example
└── README.md
```

## Instalación local

```bash
# 1. Clonar el repositorio
git clone https://github.com/TU_USUARIO/canslim-scanner.git
cd canslim-scanner

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno (opcional, solo para FMP)
cp .env.example .env
# edita .env con tu FMP_API_KEY si lo usas

# 4. Correr el scanner
python -m scanner.runner
```

## Uso

```bash
# Universo por defecto (~80 líderes de mercado)
python -m scanner.runner

# Tickers específicos
python -m scanner.runner --tickers NVDA AAPL MSFT

# S&P 500 completo (tarda ~5 min)
python -m scanner.runner --universe sp500

# Modo estricto (score >= 27)
python -m scanner.runner --strict

# Con fuente FMP (más preciso, requiere API key)
python -m scanner.runner --source fmp
```

## Ajustar umbrales

Todos los parámetros viven en `scanner/config.py`. Cada criterio tiene su propia clase de configuración:

```python
from scanner.config import cfg

# Cambiar umbral mínimo de EPS trimestral
cfg.c.eps_growth_min = 0.30  # 30% en vez de 25%

# Cambiar umbral de ROE
cfg.a.roe_min = 0.20  # 20% en vez de 17%
```

## Despliegue en GitHub Actions

El workflow `.github/workflows/scanner.yml` corre automáticamente de lunes a viernes a las 21:15 UTC (5:15pm hora del Este), después del cierre del mercado. Los resultados se guardan en `data/` y se publican en GitHub Pages.

Para activarlo:
1. Haz fork o sube este repo a tu cuenta de GitHub
2. Ve a Settings → Pages → Source: `main` branch, carpeta `/web`
3. El scanner correrá automáticamente sin configuración adicional

## Fuentes de datos

- **Yahoo Finance** (por defecto) — gratuito, sin API key, suficiente para criterios técnicos y fundamentales básicos
- **Financial Modeling Prep** — más preciso para earnings, earnings surprise, e institucionales. Plan gratuito: 250 requests/día. [Obtener clave](https://financialmodelingprep.com)

## Limitaciones conocidas

- Los datos de institucionales de yfinance tienen delay de ~45 días (reporte 13F trimestral)
- El earnings surprise (beat/miss) requiere FMP para datos precisos
- El RS Rating oficial de IBD no está disponible — se usa RS casero calculado vs SPX

---

Construido con Python · yfinance · GitHub Actions · GitHub Pages
