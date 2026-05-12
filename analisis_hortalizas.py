"""
Análisis de la importancia comercial y social de las principales hortalizas
producidas en México, basado en datos de FAOSTAT (dataset QCL).

Fuente: FAO. 2025. FAOSTAT - Crops and livestock products.
        https://www.fao.org/faostat/en/#data/QCL

Script autocontenido: descarga sus propios datos e instala sus dependencias
si no están disponibles. Sólo requiere Python >= 3.8.
"""

import importlib
import importlib.util
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


# --------------------------------------------------------------------------- #
# 0. AUTO-INSTALL DE DEPENDENCIAS                                             #
#    Si falta alguna librería:                                                #
#      1) intenta usar el `pip` del intérprete actual                         #
#      2) si no hay pip, intenta `ensurepip`                                  #
#      3) si ensurepip está deshabilitado (Debian/Ubuntu),                    #
#         crea un .venv local y reejecuta el script dentro                    #
# --------------------------------------------------------------------------- #
REQUIRED = [("pandas", "pandas"), ("numpy", "numpy"),
            ("matplotlib", "matplotlib"), ("seaborn", "seaborn")]

_SCRIPT_DIR = Path(__file__).resolve().parent
_VENV_DIR = _SCRIPT_DIR / ".venv"


def _pip_available():
    try:
        importlib.import_module("pip")
        return True
    except ImportError:
        return False


def _try_ensurepip():
    # ensurepip.bootstrap() puede lanzar SystemExit en Debian/Ubuntu, donde
    # está deshabilitado intencionalmente. Capturamos BaseException para que
    # cualquier fallo (incluido SystemExit) caiga al plan B (venv).
    try:
        import ensurepip
        # Redirigir stderr temporalmente para no contaminar la consola con
        # el mensaje "ensurepip is disabled" cuando vamos a fallar igualmente.
        with open(os.devnull, "w") as devnull:
            old_stderr = sys.stderr
            sys.stderr = devnull
            try:
                ensurepip.bootstrap()
            finally:
                sys.stderr = old_stderr
        return _pip_available()
    except BaseException:
        return False


def _reexec_in_venv():
    """Crea (si hace falta) un venv junto al script y se reejecuta dentro."""
    venv_python = _VENV_DIR / "bin" / "python3"
    if not venv_python.exists():
        print(f"[setup] Creando entorno virtual local en {_VENV_DIR} ...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "venv", str(_VENV_DIR)]
            )
        except subprocess.CalledProcessError:
            raise SystemExit(
                "[setup] No se pudo crear el entorno virtual. En Debian/Ubuntu "
                "puede que necesites: sudo apt install python3-venv"
            )
    print(f"[setup] Reejecutando dentro del venv: {venv_python}")
    os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve())])


def _pip_install(pkg):
    """Instala `pkg` con fallbacks para entornos PEP 668."""
    base = [sys.executable, "-m", "pip", "install", "--quiet", pkg]
    for extra in ([], ["--user"], ["--user", "--break-system-packages"]):
        try:
            subprocess.check_call(base + extra)
            return
        except subprocess.CalledProcessError:
            continue
    raise SystemExit(
        f"[setup] No se pudo instalar '{pkg}'. Instálalo manualmente con:\n"
        f"        {sys.executable} -m pip install {pkg}"
    )


def _ensure_dependencies():
    """Garantiza que todas las dependencias estén importables."""
    missing = [(p, m) for p, m in REQUIRED
               if importlib.util.find_spec(m) is None]
    if not missing:
        return

    if not _pip_available() and not _try_ensurepip():
        # En Debian/Ubuntu ensurepip está deshabilitado; usa venv.
        _reexec_in_venv()  # no regresa de aquí

    for pkg, mod in missing:
        print(f"[setup] Instalando dependencia faltante: {pkg} ...")
        _pip_install(pkg)
        importlib.import_module(mod)


_ensure_dependencies()

import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                 # noqa: E402
import pandas as pd                # noqa: E402
import seaborn as sns              # noqa: E402


# --------------------------------------------------------------------------- #
# Rutas: relativas a la ubicación del script (repo-portable)                  #
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "Production_Crops_Livestock_E_Americas_NOFLAG.csv"
FIG_DIR = BASE_DIR / "figuras"
FIG_DIR.mkdir(exist_ok=True)

CONTINENTS = ["Americas", "Asia", "Europe", "Africa", "Oceania"]
DATA_URL_TEMPLATE = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_{continent}.zip"
)


def _continent_csv(continent):
    return DATA_DIR / f"Production_Crops_Livestock_E_{continent}_NOFLAG.csv"


def ensure_data():
    """Descarga + descomprime los bulks de FAOSTAT (todos los continentes)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for continent in CONTINENTS:
        csv_path = _continent_csv(continent)
        if csv_path.exists():
            continue
        url = DATA_URL_TEMPLATE.format(continent=continent)
        zip_path = DATA_DIR / f"Production_Crops_Livestock_E_{continent}.zip"
        print(f"[setup] Descargando {continent} de FAOSTAT ({url}) ...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as out:
            out.write(resp.read())
        print(f"[setup] Descomprimiendo {zip_path.name} ...")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(DATA_DIR)
        if not csv_path.exists():
            raise FileNotFoundError(
                f"No se encontró {csv_path} después de descomprimir el ZIP."
            )

MEXICO_AREA_CODE = 138
YEAR_START, YEAR_END = 2000, 2023

# Element codes
EL_PROD = 5510   # Production (t)
EL_AREA = 5312   # Area harvested (ha)
EL_YIELD = 5412  # Yield (kg/ha) in the 2025 FAOSTAT release -> convert to t/ha by /1000
                 # (the historical code 5419 used hg/ha but is no longer published for crops)

# Target crops: (FAOSTAT Item Code, Spanish name)
# Nota: la papa (Solanum tuberosum) se incluye en uso común como hortaliza
# en México, aunque FAOSTAT la agrupe como 'Roots and Tubers'. Se considera
# en este análisis por su peso productivo (~2 Mt anuales).
TARGET_CROPS = {
    388:  ("Tomate",     "Tomatoes"),
    401:  ("Chile verde","Chillies and peppers, green"),
    403:  ("Cebolla",    "Onions and shallots, dry"),
    116:  ("Papa",       "Potatoes"),
    397:  ("Pepino",     "Cucumbers and gherkins"),
    393:  ("Brócoli y coliflor", "Cauliflowers and broccoli"),
    394:  ("Calabaza",   "Pumpkins, squash and gourds"),
    358:  ("Col",        "Cabbages"),
    372:  ("Lechuga",    "Lettuce and chicory"),
    406:  ("Ajo",        "Green garlic"),
    367:  ("Espárrago",  "Asparagus"),
}

# Set publication-quality style
sns.set_theme(style="whitegrid", context="paper", font_scale=1.1)
plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.titleweight": "bold",
    "axes.titlesize": 14,
    "axes.labelsize": 11,
    "axes.labelweight": "bold",   # ejes X / Y siempre en negritas
    "font.family": "DejaVu Sans",
})

# Fixed colour per crop -> guarantees identity is preserved across all figures.
# Colours chosen to be visually distinct and, where possible, evocative.
CROP_COLORS = {
    "Tomate":             "#d62728",  # rojo  – tomate maduro
    "Chile verde":        "#2ca02c",  # verde – chile
    "Cebolla":            "#9467bd",  # morado – cebolla morada
    "Papa":               "#c4956c",  # beige tierra – papa
    "Pepino":             "#17becf",  # cian   – frescura
    "Brócoli y coliflor": "#1f77b4",  # azul   – contraste
    "Calabaza":           "#ff7f0e",  # naranja – calabaza
    "Lechuga":            "#bcbd22",  # verde lima
    "Col":                "#8c564b",  # marrón
    "Espárrago":          "#e377c2",  # rosa
    "Ajo":                "#7f7f7f",  # gris  – piel de ajo
}


def colors_for(crops):
    """Return list of crop colours in the order of the given iterable."""
    return [CROP_COLORS[c] for c in crops]


def bold_legend_title(legend):
    if legend is not None and legend.get_title() is not None:
        legend.get_title().set_fontweight("bold")


# --------------------------------------------------------------------------- #
# 1. LOAD AND RESHAPE DATA                                                    #
# --------------------------------------------------------------------------- #
def load_mexico_long():
    """Return long-format DataFrame: crop_es, crop_en, item_code, element, year, value, unit."""
    df = pd.read_csv(DATA_FILE, encoding="utf-8")
    mex = df[df["Area Code"] == MEXICO_AREA_CODE].copy()

    elements_keep = {EL_PROD: "Producción", EL_AREA: "Área", EL_YIELD: "Rendimiento"}
    mex = mex[mex["Element Code"].isin(elements_keep)]
    mex = mex[mex["Item Code"].isin(TARGET_CROPS)]

    year_cols = [f"Y{y}" for y in range(YEAR_START, YEAR_END + 1)]
    keep_cols = ["Item Code", "Item", "Element Code", "Element", "Unit"] + year_cols
    mex = mex[keep_cols]

    long = mex.melt(
        id_vars=["Item Code", "Item", "Element Code", "Element", "Unit"],
        value_vars=year_cols,
        var_name="Year",
        value_name="Value",
    )
    long["Year"] = long["Year"].str[1:].astype(int)
    long["element_es"] = long["Element Code"].map(elements_keep)
    long["crop_es"] = long["Item Code"].map(lambda c: TARGET_CROPS[c][0])
    long["crop_en"] = long["Item Code"].map(lambda c: TARGET_CROPS[c][1])

    # Convert yield from kg/ha to t/ha
    mask = long["Element Code"] == EL_YIELD
    long.loc[mask, "Value"] = long.loc[mask, "Value"] / 1000.0
    long.loc[mask, "Unit"] = "t/ha"

    return long.dropna(subset=["Value"])


def pivot(long_df, element_code):
    sub = long_df[long_df["Element Code"] == element_code]
    return sub.pivot_table(index="Year", columns="crop_es", values="Value", aggfunc="sum")


# --------------------------------------------------------------------------- #
# 2. PLOTS                                                                    #
# --------------------------------------------------------------------------- #
def plot_production_lines(prod_wide):
    """Line chart: production (t) per crop over time."""
    fig, ax = plt.subplots(figsize=(11, 6.5))
    crops_sorted = prod_wide.iloc[-1].sort_values(ascending=False).index.tolist()
    for crop in crops_sorted:
        ax.plot(prod_wide.index, prod_wide[crop] / 1e6,
                marker="o", markersize=3.5, linewidth=1.8,
                label=crop, color=CROP_COLORS[crop])
    ax.set_title(f"Producción anual de hortalizas en México ({YEAR_START}–{YEAR_END})")
    ax.set_xlabel("Año")
    ax.set_ylabel("Producción (millones de toneladas)")
    leg = ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0),
                    frameon=False, title="Hortaliza")
    bold_legend_title(leg)
    ax.set_xlim(YEAR_START - 0.5, YEAR_END + 0.5)
    ax.grid(True, alpha=0.3)
    fig.text(0.01, -0.02, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "07_produccion_lineas.png")
    plt.close(fig)


def plot_recent_ranking(prod_wide, year):
    """Horizontal bar chart: ranking by production in most recent year."""
    series = prod_wide.loc[year].sort_values(ascending=True) / 1e6
    fig, ax = plt.subplots(figsize=(9, 6))
    bars = ax.barh(series.index, series.values,
                   color=colors_for(series.index),
                   edgecolor="black", linewidth=0.4)
    for bar, val in zip(bars, series.values):
        ax.text(val + max(series.values) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:,.2f}", va="center", fontsize=9)
    ax.set_title(f"Ranking de hortalizas mexicanas por producción ({year})")
    ax.set_xlabel("Producción (millones de toneladas)")
    ax.set_ylabel("")
    ax.set_xlim(0, max(series.values) * 1.15)
    fig.text(0.01, -0.02, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "08_ranking_reciente.png")
    plt.close(fig)


def plot_yield_evolution(yield_wide):
    """Yield evolution (t/ha) over time."""
    crops_sorted = yield_wide.mean().sort_values(ascending=False).index.tolist()
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for crop in crops_sorted:
        ax.plot(yield_wide.index, yield_wide[crop],
                marker="o", markersize=3.5, linewidth=1.8,
                label=crop, color=CROP_COLORS[crop])
    ax.set_title(f"Evolución del rendimiento de las hortalizas en México ({YEAR_START}–{YEAR_END})")
    ax.set_xlabel("Año")
    ax.set_ylabel("Rendimiento (t/ha)")
    leg = ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0),
                    frameon=False, title="Hortaliza")
    bold_legend_title(leg)
    fig.text(0.01, -0.02, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "10_rendimiento_lineas.png")
    plt.close(fig)


def plot_share_stacked(prod_wide):
    """Stacked area: relative share (%) of total horticultural production by crop."""
    share = prod_wide.div(prod_wide.sum(axis=1), axis=0) * 100
    crops_sorted = share.iloc[-1].sort_values(ascending=False).index.tolist()
    share = share[crops_sorted]
    fig, ax = plt.subplots(figsize=(11, 6.5))
    palette = colors_for(share.columns)
    ax.stackplot(share.index, share.T.values, labels=share.columns,
                 colors=palette, alpha=0.85, edgecolor="white", linewidth=0.4)
    ax.set_title("Participación relativa de cada hortaliza en la producción nacional")
    ax.set_xlabel("Año")
    ax.set_ylabel("Participación (%)")
    ax.set_ylim(0, 100)
    ax.set_xlim(YEAR_START, YEAR_END)
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=palette[i], label=c) for i, c in enumerate(share.columns)]
    leg = ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0),
                    frameon=False, title="Hortaliza")
    bold_legend_title(leg)
    fig.text(0.01, -0.02, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "09_participacion_apilada.png")
    plt.close(fig)


def plot_area_vs_yield(area_wide, yield_wide, prod_wide, year):
    """Scatter: area (ha) vs yield (t/ha) in most recent year, bubble size = production."""
    df = pd.DataFrame({
        "area": area_wide.loc[year],
        "yield": yield_wide.loc[year],
        "prod": prod_wide.loc[year],
    }).dropna()

    fig, ax = plt.subplots(figsize=(10, 7))
    sizes = (df["prod"] / df["prod"].max()) * 1800 + 60
    scatter = ax.scatter(df["area"] / 1000, df["yield"], s=sizes,
                         c=colors_for(df.index), alpha=0.75,
                         edgecolors="black", linewidth=0.8)
    for crop, row in df.iterrows():
        ax.annotate(crop, (row["area"] / 1000, row["yield"]),
                    xytext=(6, 6), textcoords="offset points",
                    fontsize=10, fontweight="bold")
    ax.set_title(f"Área cosechada vs. rendimiento de las hortalizas mexicanas ({year})\n(el tamaño del círculo indica la producción total)")
    ax.set_xlabel("Área cosechada (miles de ha)")
    ax.set_ylabel("Rendimiento (t/ha)")
    ax.grid(True, alpha=0.3)
    fig.text(0.01, -0.02, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "11_area_vs_rendimiento.png")
    plt.close(fig)


def plot_growth_bars(prod_wide):
    """Bar chart: growth (%) in production between the first 3-yr average and the last 3-yr average."""
    early = prod_wide.iloc[:3].mean()
    late = prod_wide.iloc[-3:].mean()
    growth = ((late - early) / early * 100).sort_values()
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ["#d73027" if v < 0 else "#1a9850" for v in growth.values]
    bars = ax.barh(growth.index, growth.values, color=colors, edgecolor="black", linewidth=0.4)
    for bar, val in zip(bars, growth.values):
        offset = max(abs(growth.values)) * 0.02 * (1 if val >= 0 else -1)
        ax.text(val + offset, bar.get_y() + bar.get_height() / 2,
                f"{val:+.1f}%", va="center",
                ha="left" if val >= 0 else "right", fontsize=9)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title("Crecimiento de la producción de hortalizas en México\n(promedio 2000–2002 vs. 2021–2023)")
    ax.set_xlabel("Crecimiento de la producción (%)")
    ax.set_xlim(min(0, growth.min() * 1.2), growth.max() * 1.18)
    fig.text(0.01, -0.02, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "12_crecimiento_porcentual.png")
    plt.close(fig)


def plot_heatmap(prod_wide):
    """Heatmap: crop x year, value = production (Mt)."""
    data = (prod_wide / 1e6).T
    data = data.loc[data.mean(axis=1).sort_values(ascending=False).index]
    fig, ax = plt.subplots(figsize=(13, 6))
    sns.heatmap(data, cmap="YlGnBu", linewidths=0.3, linecolor="white",
                cbar_kws={"label": "Producción (millones de t)"},
                ax=ax, annot=False)
    ax.set_title(f"Mapa de calor de la producción anual por hortaliza ({YEAR_START}–{YEAR_END})")
    ax.set_xlabel("Año")
    ax.set_ylabel("")
    fig.text(0.01, -0.02, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "13_heatmap_produccion.png")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 3. SUMMARY TABLE                                                            #
# --------------------------------------------------------------------------- #
def build_summary(long_df, recent_year):
    rows = []
    for item_code, (es, en) in TARGET_CROPS.items():
        sub = long_df[long_df["Item Code"] == item_code]
        if sub.empty:
            continue
        prod = sub[sub["Element Code"] == EL_PROD]["Value"]
        area = sub[sub["Element Code"] == EL_AREA]["Value"]
        yld = sub[sub["Element Code"] == EL_YIELD]["Value"]
        rows.append({
            "Cultivo (ES)": es,
            "Crop (EN)": en,
            "Producción promedio (t)": round(prod.mean(), 1) if len(prod) else np.nan,
            "Área promedio (ha)": round(area.mean(), 1) if len(area) else np.nan,
            "Rendimiento promedio (t/ha)": round(yld.mean(), 2) if len(yld) else np.nan,
            f"Producción {recent_year} (t)": round(
                sub[(sub["Element Code"] == EL_PROD) & (sub["Year"] == recent_year)]["Value"].sum(), 1),
            "Año más reciente con datos":
                int(sub[sub["Element Code"] == EL_PROD]["Year"].max()),
        })
    out = pd.DataFrame(rows).sort_values("Producción promedio (t)", ascending=False)
    out.to_csv(BASE_DIR / "figuras" / "tabla_resumen_hortalizas.csv", index=False)
    return out


# --------------------------------------------------------------------------- #
# 3-BIS. COMPARACIÓN CON OTROS GRUPOS DE PLANTAS (México)                     #
# --------------------------------------------------------------------------- #
# Agregados oficiales FAOSTAT (códigos de item)
PLANT_GROUPS = {
    1735: ("Hortalizas",      "#2ca02c"),
    1738: ("Frutas",          "#ff7f0e"),
    1717: ("Cereales",        "#8c564b"),
    1726: ("Leguminosas",     "#9467bd"),
    1720: ("Raíces y tubérc.","#bcbd22"),
    1732: ("Oleaginosas",     "#17becf"),
    1729: ("Frutos secos",    "#e377c2"),
    1723: ("Cult. azucareras","#d62728"),
}


def load_mexico_groups():
    """Producción anual (t) por grupo de plantas en México."""
    df = pd.read_csv(_continent_csv("Americas"), encoding="utf-8")
    mex = df[df["Area Code"] == MEXICO_AREA_CODE]
    mex = mex[(mex["Element Code"] == EL_PROD) &
              (mex["Item Code"].isin(PLANT_GROUPS))]
    year_cols = [f"Y{y}" for y in range(YEAR_START, YEAR_END + 1)]
    out = mex.set_index("Item Code")[year_cols]
    out.columns = [int(c[1:]) for c in out.columns]
    out.index = [PLANT_GROUPS[c][0] for c in out.index]
    return out  # filas = grupo, columnas = año


def plot_groups_ranking(groups_wide, year):
    """Producción por grupo en un año dado."""
    series = (groups_wide[year] / 1e6).sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = [PLANT_GROUPS[k][1] for k, (n, _) in PLANT_GROUPS.items()
              for s_name in [n] if s_name in series.index]
    # Map colours by name for safety
    color_map = {n: c for _, (n, c) in PLANT_GROUPS.items()}
    bars = ax.barh(series.index, series.values,
                   color=[color_map[n] for n in series.index],
                   edgecolor="black", linewidth=0.4)
    for bar, val in zip(bars, series.values):
        ax.text(val + max(series.values) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{val:,.1f}", va="center", fontsize=9)
    ax.set_title(f"Producción de grupos de plantas en México ({year})")
    ax.set_xlabel("Producción (millones de toneladas)")
    ax.set_ylabel("")
    ax.set_xlim(0, max(series.values) * 1.15)
    fig.text(0.01, -0.02,
             "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL · agregados oficiales",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "04_grupos_plantas_mexico.png")
    plt.close(fig)


def plot_groups_evolution(groups_wide):
    """Evolución de la producción de cada grupo (2000–2023)."""
    fig, ax = plt.subplots(figsize=(11, 6.5))
    color_map = {n: c for _, (n, c) in PLANT_GROUPS.items()}
    order = groups_wide.iloc[:, -1].sort_values(ascending=False).index
    for group in order:
        ax.plot(groups_wide.columns, groups_wide.loc[group] / 1e6,
                marker="o", markersize=3.5, linewidth=1.8,
                label=group, color=color_map[group])
    ax.set_title(f"Evolución de la producción de grupos de plantas en México ({YEAR_START}–{YEAR_END})")
    ax.set_xlabel("Año")
    ax.set_ylabel("Producción (millones de toneladas)")
    leg = ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0),
                    frameon=False, title="Grupo")
    bold_legend_title(leg)
    fig.text(0.01, -0.02,
             "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL · agregados oficiales",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "05_grupos_evolucion.png")
    plt.close(fig)


CROP_ES_TRANSLATIONS = {
    "Sugar cane": "Caña de azúcar",
    "Maize (corn)": "Maíz",
    "Oranges": "Naranja",
    "Sorghum": "Sorgo",
    "Tomatoes": "Tomate",
    "Chillies and peppers, green (Capsicum spp. and Pimenta spp.)":
        "Chile verde",
    "Chillies and peppers, green": "Chile verde",
    "Wheat": "Trigo",
    "Lemons and limes": "Limón y lima",
    "Avocados": "Aguacate",
    "Mangoes, guavas and mangosteens": "Mango, guayaba y mangostán",
    "Bananas": "Plátano",
    "Potatoes": "Papa",
    "Onions and shallots, dry (excluding dehydrated)": "Cebolla",
    "Onions and shallots, dry": "Cebolla",
    "Watermelons": "Sandía",
    "Oil palm fruit": "Fruto de palma de aceite",
    "Pineapples": "Piña",
    "Papayas": "Papaya",
    "Green corn (maize)": "Elote",
    "Coconuts, in shell": "Coco con cáscara",
    "Cucumbers and gherkins": "Pepino",
    "Strawberries": "Fresa",
    "Tangerines, mandarins, clementines": "Mandarina",
    "Cauliflowers and broccoli": "Brócoli y coliflor",
    "Asparagus": "Espárrago",
    "Lettuce and chicory": "Lechuga",
    "Cabbages": "Col",
    "Pumpkins, squash and gourds": "Calabaza",
    "Green garlic": "Ajo",
}


def _es_crop(name):
    """Traduce nombre de cultivo a español (con limpieza de paréntesis)."""
    if name in CROP_ES_TRANSLATIONS:
        return CROP_ES_TRANSLATIONS[name]
    # Quitar cualquier paréntesis y sus contenidos como fallback.
    import re
    return re.sub(r"\s*\([^)]*\)\s*", "", name).strip()


def plot_top20_crops_mexico(year):
    """Top 20 cultivos individuales en México por producción."""
    df = pd.read_csv(_continent_csv("Americas"), encoding="utf-8")
    mex = df[(df["Area Code"] == MEXICO_AREA_CODE) &
             (df["Element Code"] == EL_PROD)].copy()
    # Solo cultivos vegetales (CPC clase '01...'); excluye animales,
    # productos procesados y agregados FAO.
    mex["cpc"] = mex["Item Code (CPC)"].astype(str).str.strip("'").fillna("")
    mex = mex[mex["cpc"].str.startswith("01")]
    mex = mex[~mex["Item Code"].astype(str).str.match(r"^17\d{2}$|^16\d{2}$")]
    top20 = (mex.sort_values(f"Y{year}", ascending=False)
                .head(20)[["Item", "Item Code", f"Y{year}"]]
                .dropna(subset=[f"Y{year}"]))
    top20["Item_ES"] = top20["Item"].map(_es_crop)
    series = top20.set_index("Item_ES")[f"Y{year}"] / 1e6
    is_veg = [c in TARGET_CROPS for c in top20["Item Code"]]

    fig, ax = plt.subplots(figsize=(11, 9))
    colors = ["#2ca02c" if v else "#cccccc" for v in is_veg]
    bars = ax.barh(series.index[::-1], series.values[::-1],
                   color=colors[::-1], edgecolor="black", linewidth=0.4)
    for bar, val in zip(bars, series.values[::-1]):
        ax.text(val + max(series.values) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{val:,.1f}", va="center", fontsize=8)
    ax.set_title(f"Top 20 cultivos individuales en México por producción ({year})")
    ax.set_xlabel("Producción (millones de toneladas)")
    ax.set_ylabel("")
    from matplotlib.patches import Patch
    leg = ax.legend(handles=[Patch(facecolor="#2ca02c", label="Hortaliza analizada"),
                             Patch(facecolor="#cccccc", label="Otro cultivo")],
                    loc="lower right", frameon=True, title="Tipo")
    bold_legend_title(leg)
    fig.text(0.01, -0.01, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "06_top20_cultivos_mexico.png")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 3-TER. COMPARACIÓN INTERNACIONAL                                            #
# --------------------------------------------------------------------------- #
# Códigos FAOSTAT que representan agregados regionales (deben excluirse de
# rankings por país). En el bulk los agregados llevan códigos >= 5000 y
# nombres como "World", "Africa", "Northern America", etc.
def _country_filter(df):
    """Conserva solo filas de países (excluye regiones, agregados, China>)."""
    return df[df["Area Code"] < 5000].copy()


def load_world_long(item_codes, element_code, year):
    """Devuelve DataFrame con Area, Item Code, valor (un año, un elemento, varios items)."""
    frames = []
    year_col = f"Y{year}"
    for cont in CONTINENTS:
        df = pd.read_csv(_continent_csv(cont), encoding="utf-8",
                         usecols=["Area Code", "Area", "Item Code", "Item",
                                  "Element Code", year_col])
        df = df[(df["Element Code"] == element_code) &
                (df["Item Code"].isin(item_codes))]
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out = _country_filter(out)
    return out.rename(columns={year_col: "value"})


COUNTRY_ES = {
    "China, mainland": "China",
    "India": "India",
    "United States of America": "Estados Unidos",
    "Türkiye": "Turquía",
    "Egypt": "Egipto",
    "Viet Nam": "Vietnam",
    "Mexico": "México",
    "Nigeria": "Nigeria",
    "Russian Federation": "Rusia",
    "Indonesia": "Indonesia",
    "Spain": "España",
    "Uzbekistan": "Uzbekistán",
    "Italy": "Italia",
    "Japan": "Japón",
    "Iran (Islamic Republic of)": "Irán",
    "Republic of Korea": "Corea del Sur",
    "Brazil": "Brasil",
    "Pakistan": "Pakistán",
    "Philippines": "Filipinas",
    "Ukraine": "Ucrania",
    "Germany": "Alemania",
    "France": "Francia",
    "Poland": "Polonia",
    "Netherlands (Kingdom of the)": "Países Bajos",
    "United Kingdom of Great Britain and Northern Ireland": "Reino Unido",
    "Republic of Moldova": "Moldavia",
    "Bangladesh": "Bangladés",
    "Algeria": "Argelia",
    "Morocco": "Marruecos",
    "South Africa": "Sudáfrica",
    "Cameroon": "Camerún",
    "Kenya": "Kenia",
    "Ethiopia": "Etiopía",
    "Ghana": "Ghana",
    "Côte d'Ivoire": "Costa de Marfil",
    "Democratic Republic of the Congo": "República Democrática del Congo",
    "Argentina": "Argentina",
    "Chile": "Chile",
    "Peru": "Perú",
    "Colombia": "Colombia",
    "Australia": "Australia",
    "New Zealand": "Nueva Zelanda",
    "Greece": "Grecia",
    "Romania": "Rumanía",
    "Belgium": "Bélgica",
    "Portugal": "Portugal",
}


def _es_country(name):
    return COUNTRY_ES.get(name, name)


def plot_world_vegetable_ranking(year, top_n=15):
    """Top N países productores de hortalizas + posición de México."""
    df = load_world_long({1735}, EL_PROD, year).dropna(subset=["value"])
    df = df.sort_values("value", ascending=False).reset_index(drop=True)
    # Renombrar China para evitar duplicados (FAOSTAT publica 'China' y
    # 'China, mainland'; nos quedamos sólo con mainland que es comparable a otros países).
    df = df[df["Area"] != "China"]
    df = df.sort_values("value", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    mex_row = df[df["Area Code"] == MEXICO_AREA_CODE].iloc[0]
    top = df.head(top_n).copy()
    if mex_row["rank"] > top_n:
        top = pd.concat([top, mex_row.to_frame().T], ignore_index=True)
    # Plot (orden ascendente, México en rojo)
    top = top.iloc[::-1]
    labels = [_es_country(a) for a in top["Area"]]
    colors = ["#d62728" if a == "Mexico" else "#4c72b0" for a in top["Area"]]
    fig, ax = plt.subplots(figsize=(11, 7))
    bars = ax.barh(labels, top["value"].astype(float) / 1e6,
                   color=colors, edgecolor="black", linewidth=0.4)
    for bar, v in zip(bars, top["value"].astype(float) / 1e6):
        ax.text(v + max(top["value"].astype(float)) / 1e6 * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{v:,.1f}", va="center", fontsize=8.5)
    ax.set_title(f"Top {top_n} productores mundiales de hortalizas (Vegetables Primary, {year})")
    ax.set_xlabel("Producción (millones de toneladas)")
    fig.text(0.01, -0.02,
             "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL · agregado 'Vegetables Primary'",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "01_top_paises_hortalizas.png")
    plt.close(fig)
    return mex_row["rank"], df["value"].sum(), mex_row["value"]


def plot_mexico_global_share(year):
    """% de la producción mundial que aporta México para cada hortaliza objetivo."""
    target_codes = set(TARGET_CROPS.keys())
    df = load_world_long(target_codes, EL_PROD, year).dropna(subset=["value"])
    df = df[df["Area"] != "China"]
    # Suma mundial y producción mexicana por item
    world = df.groupby("Item Code")["value"].sum()
    mex = df[df["Area Code"] == MEXICO_AREA_CODE].set_index("Item Code")["value"]
    rank = df.sort_values("value", ascending=False).groupby("Item Code").apply(
        lambda g: g.reset_index(drop=True).index[g["Area Code"].values
                                                 == MEXICO_AREA_CODE].tolist()[0] + 1,
        include_groups=False,
    )
    share = (mex / world * 100).sort_values(ascending=True)

    fig, ax = plt.subplots(figsize=(11, 6.5))
    crop_names = [TARGET_CROPS[c][0] for c in share.index]
    bars = ax.barh(crop_names, share.values,
                   color=[CROP_COLORS[n] for n in crop_names],
                   edgecolor="black", linewidth=0.4)
    for bar, v, code in zip(bars, share.values, share.index):
        r = rank.get(code, "—")
        ax.text(v + max(share.values) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}% · rank mundial #{r}",
                va="center", fontsize=9)
    ax.set_title(f"Participación de México en la producción mundial por hortaliza ({year})")
    ax.set_xlabel("Participación de México (%)")
    ax.set_xlim(0, max(share.values) * 1.30)
    fig.text(0.01, -0.02, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "02_mexico_share_mundial.png")
    plt.close(fig)
    return share, rank


def plot_mexico_vs_world_yield(year):
    """Compara rendimiento (t/ha) de México vs promedio mundial ponderado por producción."""
    target_codes = set(TARGET_CROPS.keys())
    prod = load_world_long(target_codes, EL_PROD, year).dropna(subset=["value"])
    area = load_world_long(target_codes, EL_AREA, year).dropna(subset=["value"])
    prod = prod[prod["Area"] != "China"]
    area = area[area["Area"] != "China"]

    # Rendimiento mundial ponderado: prod_total / area_total
    world = (prod.groupby("Item Code")["value"].sum() /
             area.groupby("Item Code")["value"].sum())
    mex_prod = prod[prod["Area Code"] == MEXICO_AREA_CODE].set_index("Item Code")["value"]
    mex_area = area[area["Area Code"] == MEXICO_AREA_CODE].set_index("Item Code")["value"]
    mex_y = mex_prod / mex_area

    data = pd.DataFrame({"México": mex_y, "Mundo (ponderado)": world}).dropna()
    data.index = [TARGET_CROPS[c][0] for c in data.index]
    data = data.sort_values("México", ascending=True)

    fig, ax = plt.subplots(figsize=(11, 6.5))
    y_pos = np.arange(len(data))
    h = 0.4
    ax.barh(y_pos + h/2, data["México"], h, label="México",
            color="#d62728", edgecolor="black", linewidth=0.3)
    ax.barh(y_pos - h/2, data["Mundo (ponderado)"], h, label="Mundo (prom. ponderado)",
            color="#4c72b0", edgecolor="black", linewidth=0.3)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(data.index)
    ax.set_title(f"Rendimiento: México vs promedio mundial ponderado ({year})")
    ax.set_xlabel("Rendimiento (t/ha)")
    leg = ax.legend(loc="lower right", frameon=True, title="Referencia")
    bold_legend_title(leg)
    fig.text(0.01, -0.02, "Fuente: FAOSTAT (FAO, 2025) · conjunto QCL",
             fontsize=8, color="grey")
    fig.savefig(FIG_DIR / "03_rendimiento_mexico_vs_mundo.png")
    plt.close(fig)
    return data


# --------------------------------------------------------------------------- #
# MAIN                                                                        #
# --------------------------------------------------------------------------- #
def main():
    ensure_data()
    long = load_mexico_long()
    prod_wide = pivot(long, EL_PROD)
    area_wide = pivot(long, EL_AREA)
    yield_wide = pivot(long, EL_YIELD)

    recent_year = int(prod_wide.index.max())
    print(f"\n--- Periodo analizado: {YEAR_START}–{recent_year} ---\n")

    # Figuras generadas de lo más general (panorama mundial) a lo más específico
    # (cultivos individuales en México).

    # 01–03 · México vs el mundo
    print("=== Figuras 01–03: México vs el mundo ===")
    mex_rank, world_total, mex_total = plot_world_vegetable_ranking(recent_year)
    print(f"México ocupa el lugar #{int(mex_rank)} mundial en producción de hortalizas")
    print(f"  · Producción mundial total ({recent_year}): {world_total/1e6:,.1f} Mt")
    print(f"  · Producción de México   ({recent_year}): {mex_total/1e6:,.1f} Mt "
          f"({mex_total/world_total*100:.2f}% mundial)")
    share, rank = plot_mexico_global_share(recent_year)
    print("\nParticipación de México en producción mundial por hortaliza:")
    for code in share.sort_values(ascending=False).index:
        name = TARGET_CROPS[code][0]
        print(f"  · {name:<22}  share = {share[code]:5.1f}%   rank mundial = #{rank.get(code,'—')}")
    yield_cmp = plot_mexico_vs_world_yield(recent_year)
    yield_cmp.to_csv(FIG_DIR / "tabla_rendimiento_mex_vs_mundo.csv")

    # 04–06 · Hortalizas dentro del agro mexicano
    print("\n=== Figuras 04–06: Hortalizas dentro del agro mexicano ===")
    groups = load_mexico_groups()
    plot_groups_ranking(groups, recent_year)
    plot_groups_evolution(groups)
    plot_top20_crops_mexico(recent_year)
    print(groups[recent_year].sort_values(ascending=False).map(
        lambda v: f"{v/1e6:,.2f} Mt").to_string())

    # 07–13 · Análisis de las 10 hortalizas objetivo en México
    print("\n=== Figuras 07–13: Las 10 hortalizas objetivo en México ===")
    plot_production_lines(prod_wide)
    plot_recent_ranking(prod_wide, recent_year)
    plot_share_stacked(prod_wide)
    plot_yield_evolution(yield_wide)
    plot_area_vs_yield(area_wide, yield_wide, prod_wide, recent_year)
    plot_growth_bars(prod_wide)
    plot_heatmap(prod_wide)

    # Tabla resumen
    summary = build_summary(long, recent_year)
    print("\n=== TABLA RESUMEN ===")
    print(summary.to_string(index=False))

    # Top 5 por producción promedio
    top5 = summary.head(5)
    print("\n=== TOP 5 CULTIVOS POR PRODUCCIÓN PROMEDIO ===")
    for i, row in enumerate(top5.itertuples(index=False), start=1):
        print(f"{i}. {row[0]:<22} ({row[1]:<32}): "
              f"{row[2]/1e6:.2f} Mt promedio · {row[5]/1e6:.2f} Mt en {recent_year}")

    print(f"\nFiguras guardadas en: {FIG_DIR}")
    print(f"CSV guardado en:      {FIG_DIR / 'tabla_resumen_hortalizas.csv'}")


if __name__ == "__main__":
    main()
