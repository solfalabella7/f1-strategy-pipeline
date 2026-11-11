"""Construye la aplicación web de la Entrega 4 a partir del pipeline y del modelo.

Uso (desde la raíz del repositorio, con el entorno de .venv):

    python build_app.py              # reconstruye la app con los datos actuales
    python build_app.py --seleccion  # además recalcula la selección de modelos (≈12 min)

Qué hace, en orden:

1. Lee ``include/output/silver/f1_silver_dataset.csv`` (capa Silver del pipeline) y las
   paradas (``f1_silver_pit_stops.csv`` o, si no está, las arma desde la capa Bronce con
   ``resolve_driver_pits`` de ``src/silver_pipeline.py``).
2. Aplica la preparación de la v6 (``src/modelo.py``) y entrena los dos random forest
   elegidos en la Entrega 3 con semilla 42.
3. Recalcula el umbral con la regla de la v6, evalúa sobre 2025 y lee los errores
   (``src/analisis_app.py``). Compara cada número con los de la v6 y lo informa.
4. Exporta los modelos a JSON, verifica con Node.js que la versión del navegador da
   lo mismo que ``predict_proba`` y guarda los ``.joblib`` en ``Entrega4/artefactos``.
5. Genera los gráficos (Altair), los datos de la sección «Explorá» y la página en
   ``Entrega4/sitio``, lista para publicar en GitHub Pages.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import time
import warnings
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

import altair as alt  # noqa: E402
import jinja2  # noqa: E402
import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import sklearn  # noqa: E402

from src import analisis_app as A  # noqa: E402
from src import exportar_modelo as EX  # noqa: E402
from src import graficos as G  # noqa: E402
from src import modelo as M  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
warnings.filterwarnings("ignore", category=UserWarning)

DIR_APP = RAIZ / "Entrega4" / "app"
DIR_SITIO = RAIZ / "Entrega4" / "sitio"
DIR_ART = RAIZ / "Entrega4" / "artefactos"
JSON_SELECCION = DIR_ART / "seleccion_v6.json"

# Números publicados en Entrega3/Entrega3_F1_v6.ipynb (salidas guardadas, scikit-learn 1.6.1).
REFERENCIA_V6 = {
    "vueltas sin etiqueta descartadas": 6627,
    "vueltas válidas": 70746,
    "paradas reales": 2333,
    "pilotos corregidos (Bélgica 2025)": 20,
    "población (vueltas con historia)": 69472,
    "paradas con compuesto": 2244,
    "umbral elegido (OOF)": 0.475,
    "test · F1 clase para": 0.1279,
    "test · precisión": 0.0724,
    "test · recall": 0.5486,
    "test · alarmas": 6077,
    "test · F1 macro compuesto": 0.6378,
    "test · accuracy compuesto": 0.6409,
    "sistema · ambas correctas": 342,
    "episodios de alarma": 641,
    "episodios que terminan en parada": 0.705,
    "CV · F1 parada (bosque elegido)": 0.1457,
    "CV · F1 macro compuesto (bosque elegido)": 0.5608,
    "CV · diferencia bosque − logística (parada)": 0.0392,
    "CV · diferencia bosque − logística (compuesto)": 0.0489,
}

NOMBRES_ES = {
    "Abu Dhabi Grand Prix": "Abu Dabi", "Australian Grand Prix": "Australia", "Austrian Grand Prix": "Austria",
    "Azerbaijan Grand Prix": "Azerbaiyán", "Bahrain Grand Prix": "Baréin", "Belgian Grand Prix": "Bélgica",
    "British Grand Prix": "Gran Bretaña", "Canadian Grand Prix": "Canadá", "Chinese Grand Prix": "China",
    "Dutch Grand Prix": "Países Bajos", "Emilia Romagna Grand Prix": "Emilia-Romaña", "Hungarian Grand Prix": "Hungría",
    "Italian Grand Prix": "Italia", "Japanese Grand Prix": "Japón", "Las Vegas Grand Prix": "Las Vegas",
    "Mexico City Grand Prix": "Ciudad de México", "Miami Grand Prix": "Miami", "Monaco Grand Prix": "Mónaco",
    "Qatar Grand Prix": "Catar", "Saudi Arabian Grand Prix": "Arabia Saudita", "Singapore Grand Prix": "Singapur",
    "Spanish Grand Prix": "España", "São Paulo Grand Prix": "São Paulo", "United States Grand Prix": "Estados Unidos",
}

ETIQUETAS_VARIABLES = {
    "lap_number": "Vuelta que empieza", "tyre_age_prev": "Edad del neumático (vueltas)",
    "position_prev": "Posición", "stops_before": "Paradas ya hechas",
    "track_temperature_prev": "Temperatura de pista (°C)", "air_temperature_prev": "Temperatura del aire (°C)",
    "humidity_prev": "Humedad (%)", "used_soft": "Ya usó SOFT", "used_medium": "Ya usó MEDIUM",
    "used_hard": "Ya usó HARD", "field_soft_prev": "Pelotón en SOFT", "field_medium_prev": "Pelotón en MEDIUM",
    "field_hard_prev": "Pelotón en HARD", "field_lluvia_prev": "Pelotón en lluvia",
    "compound_prev": "Neumático puesto", "circuit_short_name": "Circuito", "team_name": "Equipo",
    "rainfall_prev": "Llueve",
}


def log(msg: str, t0: float = [time.time()]) -> None:  # noqa: B006
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


# --------------------------------------------------------------------------
# Formato en castellano
# --------------------------------------------------------------------------
def num(x, dec=0):
    s = f"{x:,.{dec}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(x, dec=0):
    return f"{num(100 * x, dec)} %"


def dec(x, d=3):
    return num(x, d)


def nombre_carrera(meeting, temporada):
    return f"{NOMBRES_ES.get(meeting, meeting)} {temporada}"


# --------------------------------------------------------------------------
# Verificación contra la v6
# --------------------------------------------------------------------------
def comparar_con_v6(obtenido: dict) -> list[dict]:
    filas = []
    for clave, ref in REFERENCIA_V6.items():
        val = obtenido[clave]
        tol = 0 if isinstance(ref, int) else (0.0005 if ref < 1 else 0.001)
        ok = abs(val - ref) <= tol
        filas.append({"numero": clave, "v6": ref, "app": round(val, 4) if isinstance(val, float) else val, "coincide": ok})
    return filas


# --------------------------------------------------------------------------
# Datos de las secciones
# --------------------------------------------------------------------------
def tabla_carreras(d: dict) -> pd.DataFrame:
    v = d["vueltas"]
    raw = d["raw"]
    fechas = raw.groupby("session_key").session_date_start.first()
    c = (v.groupby("session_key")
         .agg(meeting=("meeting_name", "first"), temporada=("season", "first"), circuito=("circuit_short_name", "first"),
              vueltas_total=("lap_number", "size"), paradas=("pit_stop", "sum"), hasta=("lap_number", "max"))
         .reset_index())
    c["fecha"] = c.session_key.map(fechas)
    c = c.sort_values("fecha").reset_index(drop=True)
    c["nombre"] = [nombre_carrera(mt, t) for mt, t in zip(c.meeting, c.temporada)]
    c["etiqueta"] = c["nombre"]
    c["desde"] = 1
    c["orden"] = np.arange(len(c))
    return c


def contexto_parada(sc: pd.Series, objetivo: pd.Series) -> np.ndarray:
    return np.select([sc, objetivo.eq("LLUVIA")], ["Con safety car", "A neumático de lluvia"], "En seco, sin safety car")


def datos_seccion_datos(d: dict, carreras: pd.DataFrame) -> pd.DataFrame:
    p = d["raw_pits"].copy()
    p["sc"] = p.safety_car_active.astype(str).str.lower().eq("true")
    p["lluvia"] = p.new_compound.isin(["INTERMEDIATE", "WET"])
    g = (p.groupby(["session_key", "lap_number"])
         .agg(paradas=("sc", "size"), sc=("sc", "any"), lluvia=("lluvia", "any")).reset_index())
    g["contexto"] = np.select([g.sc, g.lluvia], ["Con safety car", "A neumático de lluvia"], "En seco, sin safety car")
    g = g.merge(carreras[["session_key", "etiqueta", "nombre"]], on="session_key")
    return g[["etiqueta", "nombre", "lap_number", "paradas", "contexto"]]


def conteos_peloton(vueltas: pd.DataFrame) -> pd.DataFrame:
    """Cantidad de autos en cada compuesto al terminar cada vuelta (para el formulario y la ficha)."""
    cnt = pd.crosstab([vueltas.session_key, vueltas.lap_number], vueltas.current_compound)
    for c in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]:
        if c not in cnt.columns:
            cnt[c] = 0
    cnt["LLUVIA"] = cnt["INTERMEDIATE"] + cnt["WET"]
    cnt = cnt[["SOFT", "MEDIUM", "HARD", "LLUVIA"]].rename(columns=lambda c: f"n_{c.lower()}").reset_index()
    cnt["lap_number"] = cnt["lap_number"] + 1  # se usa en la vuelta siguiente, como field_*_prev
    return cnt


def redondear(v, d=4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return int(f) if f.is_integer() else round(f, d)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    return v


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seleccion", action="store_true", help="recalcular la selección de modelos (lento)")
    ap.add_argument("--sin-node", action="store_true", help="no verificar la paridad del modelo en Node.js")
    args = ap.parse_args()

    log(f"scikit-learn {sklearn.__version__} · pandas {pd.__version__} · numpy {np.__version__} · altair {alt.__version__}")
    if sklearn.__version__ != "1.6.1":
        log("AVISO: la v6 se corrió con scikit-learn 1.6.1; con otra versión pueden moverse decimales.")

    # 1-2. Datos y preparación de la v6 ---------------------------------------------------
    d = M.preparar_todo()
    info = d["info_limpieza"]
    log(f"Silver: {d['raw'].shape} · paradas: {len(d['raw_pits'])} ({d['origen_pits']})")
    mod_pit, mod_comp = A.entrenar_finales(d)
    log("Modelos finales entrenados (random forest × 2, semilla 42)")

    # 3. Umbral, test y errores --------------------------------------------------------------
    oof = A.predicciones_fuera_de_fold(d)
    Xp, yp, _ = M.split_datos(d["train"])
    umbral, tabla_umbral = A.elegir_umbral(yp.values, oof.puntaje.values)
    log(f"Umbral por la regla de la v6: {umbral}")
    res, proba_test, pred_pit, pred_comp = A.evaluar_test(d, mod_pit, mod_comp, umbral)
    L = A.lectura_errores(d, proba_test, pred_pit, pred_comp, mod_comp)
    C = A.correcciones_e3(L, proba_test, M.split_datos(d["test"])[1].values, mod_pit, mod_comp)
    h4 = A.hipotesis_4(d["raw_pits"])
    h1 = A.hipotesis_1(d, mod_comp)
    estado = h1.pop("_estado")  # variables de HistoriaCausal para toda la población

    if args.seleccion or not JSON_SELECCION.exists():
        from src import seleccion as S
        log("Recalculando la selección de modelos (familias, grillas, pareada, ablación, importancia)…")
        sel = S.calcular(d, log=log)
        DIR_ART.mkdir(parents=True, exist_ok=True)
        JSON_SELECCION.write_text(json.dumps(sel, ensure_ascii=False, indent=1), encoding="utf-8")
    sel = json.loads(JSON_SELECCION.read_text(encoding="utf-8"))

    sistema = L["sistema"]
    obtenido = {
        "vueltas sin etiqueta descartadas": info["vueltas_sin_etiqueta"], "vueltas válidas": info["vueltas_validas"],
        "paradas reales": info["paradas_reales"], "pilotos corregidos (Bélgica 2025)": info["pilotos_corregidos"],
        "población (vueltas con historia)": len(d["poblacion"]),
        "paradas con compuesto": int(d["poblacion"].pit_stop.sum()), "umbral elegido (OOF)": umbral,
        "test · F1 clase para": res["pit"]["modelo"]["f1"], "test · precisión": res["pit"]["modelo"]["precision"],
        "test · recall": res["pit"]["modelo"]["recall"], "test · alarmas": res["pit"]["modelo"]["alarmas"],
        "test · F1 macro compuesto": res["comp"]["modelo"]["f1_macro"],
        "test · accuracy compuesto": res["comp"]["modelo"]["accuracy"],
        "sistema · ambas correctas": sistema["ambas"], "episodios de alarma": L["episodios"],
        "episodios que terminan en parada": L["episodios_terminan_en_parada"],
        "CV · F1 parada (bosque elegido)": sel["elegidos_cv"][0]["f1_validacion"],
        "CV · F1 macro compuesto (bosque elegido)": sel["elegidos_cv"][1]["f1_validacion"],
        "CV · diferencia bosque − logística (parada)": sel["pareada"]["pit"]["diferencia_media"],
        "CV · diferencia bosque − logística (compuesto)": sel["pareada"]["comp"]["diferencia_media"],
    }
    verificacion = comparar_con_v6(obtenido)
    distintos = [f for f in verificacion if not f["coincide"]]
    log(f"Comparación con la v6: {len(verificacion) - len(distintos)} de {len(verificacion)} números coinciden")
    for f in distintos:
        log(f"  DIFIERE · {f['numero']}: v6 {f['v6']} · app {f['app']}")

    # 4. Modelos: JSON, paridad con Node.js y joblib ------------------------------------------
    DIR_SITIO.mkdir(parents=True, exist_ok=True)
    (DIR_SITIO / "datos" / "carreras").mkdir(parents=True, exist_ok=True)
    paridad = {}
    for nombre, mod, binario in [("parada", mod_pit, True), ("compuesto", mod_comp, False)]:
        js = EX.exportar(mod, binario)
        (DIR_SITIO / "datos" / f"modelo_{nombre}.json").write_text(json.dumps(js, separators=(",", ":")), encoding="utf-8")
        if args.sin_node:
            paridad[nombre] = {"verificado": False, "motivo": "omitido con --sin-node"}
        else:
            paridad[nombre] = EX.verificar_paridad(js, mod, estado, DIR_APP / "modelo.js")
        log(f"Modelo de {nombre} exportado · paridad con scikit-learn: {paridad[nombre]}")
    DIR_ART.mkdir(parents=True, exist_ok=True)
    for nombre, mod in [("f1_modelo_pit_stop.joblib", mod_pit), ("f1_modelo_new_compound.joblib", mod_comp)]:
        mod.set_params(historia__registro=None)
        joblib.dump(mod, DIR_ART / nombre, compress=3)
        mod.set_params(historia__registro=d["registro"])

    # 5. Datos de la app -----------------------------------------------------------------------
    carreras = tabla_carreras(d)
    pob = d["poblacion"].copy()
    pob = pd.concat([pob, estado.drop(columns=["lap_number", "circuit_short_name", "team_name"])], axis=1)
    # Predicción fuera de muestra de cada vuelta: fuera de fold (2023-2024) o modelo final (2025).
    pred = oof.drop(columns="fold").copy()
    pt = d["test"][M.CLAVE].copy()
    pt["puntaje"] = proba_test
    p_test = mod_comp.predict_proba(d["test"][M.COLS_X])
    clases = list(mod_comp.named_steps["modelo"].classes_)
    for c in M.ORDEN:
        pt[f"p_{c}"] = p_test[:, clases.index(c)]
    pred = pd.concat([pred, pt], ignore_index=True)
    pob = pob.merge(pred, on=M.CLAVE, how="left", validate="one_to_one")
    assert pob.puntaje.notna().all()
    pob["comp_pred"] = np.array(M.ORDEN)[pob[[f"p_{c}" for c in M.ORDEN]].values.argmax(1)]
    pob["sc"] = pob.safety_car_active.astype(str).str.lower().eq("true")
    pob = pob.merge(conteos_peloton(d["vueltas"]), on=["session_key", "lap_number"], how="left")
    for c in ["n_soft", "n_medium", "n_hard", "n_lluvia"]:
        pob[c] = pob[c].fillna(0).astype(int)
    pob = pob.merge(d["vueltas"][M.CLAVE + ["name_acronym"]], on=M.CLAVE, how="left")
    pob = pob.merge(carreras[["session_key", "nombre", "orden"]], on="session_key", how="left")

    # Panorama: una fila por parada real de la población
    par = pob[pob.pit_stop].copy()
    par["contexto"] = contexto_parada(par.sc, par.objetivo_compuesto)
    panorama = [{"carrera": r.nombre, "orden": int(r.orden), "temporada": int(r.season), "sk": int(r.session_key),
                 "contexto": r.contexto, "puntaje": round(float(r.puntaje), 6)} for r in par.itertuples()]
    (DIR_SITIO / "datos" / "paradas.json").write_text(json.dumps(panorama, ensure_ascii=False, separators=(",", ":")),
                                                      encoding="utf-8")

    # Un archivo por carrera con todas sus vueltas (se carga al elegirla)
    # Formato por columnas: los nombres van una vez; lo constante, por piloto o por carrera.
    # Las proporciones del pelotón (field_*_prev) se recalculan en el navegador como n / total,
    # la misma división que hace HistoriaCausal.
    indice = []
    COLS_FILA = ["piloto", "vuelta", "puntaje", "p", "comp_pred", "para", "objetivo", "sc", "tyre_age_prev", "position_prev",
                 "stops_before", "track_temperature_prev", "air_temperature_prev", "humidity_prev", "used_soft",
                 "used_medium", "used_hard", "compound_prev", "rainfall_prev", "n_soft", "n_medium", "n_hard", "n_lluvia"]
    for sk, g in pob.groupby("session_key"):
        meta = carreras.set_index("session_key").loc[sk]
        orden_pil = (g.groupby("name_acronym").lap_number.max().sort_values(ascending=False).index.tolist())
        info_pil = {a: [n, t, orden_pil.index(a), int(dn)] for a, n, t, dn in
                    g[["name_acronym", "full_name", "team_name", "driver_number"]].drop_duplicates("name_acronym").values}
        filas = []
        for r in g.sort_values(["driver_number", "lap_number"]).to_dict("records"):
            fila = {"piloto": r["name_acronym"], "vuelta": int(r["lap_number"]),
                    "puntaje": round(float(r["puntaje"]), 6),
                    "p": [round(float(r[f"p_{c}"]), 4) for c in M.ORDEN], "comp_pred": r["comp_pred"],
                    "para": int(r["pit_stop"]), "objetivo": r["objetivo_compuesto"] if r["pit_stop"] else None,
                    "sc": int(r["sc"])}
            for c in COLS_FILA[8:]:
                fila[c] = redondear(r[c], 6)
            filas.append([fila[c] for c in COLS_FILA])
        origen = "test" if int(meta.temporada) == 2025 else "oof"
        (DIR_SITIO / "datos" / "carreras" / f"{sk}.json").write_text(
            json.dumps({"sk": int(sk), "nombre": meta.nombre, "origen": origen, "circuito": meta.circuito,
                        "pilotos": info_pil, "columnas": COLS_FILA, "filas": filas},
                       ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        pilotos = (g[["name_acronym", "full_name"]].drop_duplicates().set_index("name_acronym")
                   .reindex(orden_pil).reset_index().values.tolist())
        indice.append({"sk": int(sk), "nombre": meta.nombre, "temporada": int(meta.temporada),
                       "circuito": meta.circuito, "fecha": str(meta.fecha)[:10], "orden": int(meta.orden),
                       "origen": origen, "vueltas": int(len(g)), "paradas": int(g.pit_stop.sum()),
                       "pilotos": pilotos})
    indice.sort(key=lambda c: c["orden"])

    # Formulario: rangos y categorías que vio el modelo (2023-2024)
    ent = pob[pob.season.lt(2025)]
    rangos = {}
    for c in M.NUM:
        if c.startswith("field_") or c.startswith("used_"):
            continue
        rangos[c] = {"min": float(ent[c].min()), "max": float(ent[c].max())}
    total_autos = ent[["n_soft", "n_medium", "n_hard", "n_lluvia"]].sum(axis=1)
    rangos["autos"] = {"min": int(total_autos[total_autos > 0].min()), "max": int(total_autos.max())}
    categorias = {
        "compound_prev": sorted(ent.compound_prev.dropna().unique().tolist(),
                                key=lambda c: ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"].index(c)),
        "circuit_short_name": sorted(ent.circuit_short_name.dropna().unique().tolist()),
        "team_name": sorted(ent.team_name.dropna().unique().tolist()),
    }
    # Caso inicial del formulario: la parada real de 2025 con la mediana de edad entre las anticipadas,
    # elegida de forma determinística (primera por clave).
    vp = pob[(pob.season.eq(2025)) & pob.pit_stop & (pob.puntaje >= umbral) & pob.objetivo_compuesto.ne("LLUVIA")]
    vp = vp.iloc[(vp.tyre_age_prev - vp.tyre_age_prev.median()).abs().argsort(kind="stable")]
    ini = vp.iloc[0]
    caso_inicial = {c: redondear(ini[c], 6) for c in M.FEATURES} | {
        c: int(ini[c]) for c in ["n_soft", "n_medium", "n_hard", "n_lluvia"]} | {
        "_desc": f"{ini['full_name']} · {ini['nombre']} · vuelta {int(ini['lap_number'])}",
        "_real": f"paró y montó {ini['objetivo_compuesto']}"}
    # Combinaciones raras pero reales (el formulario las avisa sin bloquearlas): frecuencia en la población.
    tot = pob[["n_soft", "n_medium", "n_hard", "n_lluvia"]].sum(axis=1)
    propio = pob.compound_prev.map({"SOFT": "n_soft", "MEDIUM": "n_medium", "HARD": "n_hard",
                                    "INTERMEDIATE": "n_lluvia", "WET": "n_lluvia"})
    n_propio = np.array([r[c] if isinstance(c, str) else 1 for c, (_, r) in zip(propio, pob.iterrows())])
    raras = {"total": int(len(pob)),
             "usados": int((pob[["used_soft", "used_medium", "used_hard"]].sum(axis=1) > pob.stops_before + 1).sum()),
             "edad": int(((pob.stops_before >= 1) & (pob.tyre_age_prev > pob.lap_number + 5)).sum()),
             "propio": int(((tot > 0) & (n_propio < 1)).sum())}
    config_app = {"raras": raras, "umbral": umbral, "orden": M.ORDEN, "rangos": rangos, "categorias": categorias,
                  "etiquetas": ETIQUETAS_VARIABLES, "caso_inicial": caso_inicial, "carreras": indice,
                  "colores": G.COLOR_COMPUESTO}

    # 6. Gráficos -------------------------------------------------------------------------------
    ctx = pd.DataFrame(L["por_contexto"])
    ctx["rotulo"] = [f"{pct(p)} · {a} de {n}" for p, a, n in zip(ctx.pct, ctx.anticipadas, ctx.paradas)]
    m_comp = pd.DataFrame(res["comp"]["matriz"], index=M.ORDEN, columns=M.ORDEN)
    mat = m_comp.reset_index().melt(id_vars="index", var_name="predicho", value_name="n").rename(columns={"index": "real"})
    mat["pct_fila"] = mat.n / mat.real.map(m_comp.sum(axis=1))
    mat["rotulo"] = [f"{n} · {pct(p)}" for n, p in zip(mat.n, mat.pct_fila)]

    def fam(k, elegido):
        t = pd.DataFrame(sel["familias"][k])
        t["elegido"] = t.modelo.eq(elegido)
        t["rotulo"] = [f"{dec(a)} ± {dec(b)}" for a, b in zip(t.f1_validacion, t.desvio)]
        return t

    # La sección «Lo que encontramos» va sobre fondo claro; el resto de la app, sobre fondo oscuro.
    G.usar_tema("claro")
    g_hallazgo = G.grafico_hallazgo(pd.DataFrame(h4["seco"]))
    g_h1 = G.grafico_h1(pd.DataFrame(h1["histograma"]))
    G.usar_tema("oscuro")
    graficos = {
        "datos": G.grafico_datos(datos_seccion_datos(d, carreras), carreras),
        "hallazgo": g_hallazgo,
        "h1": g_h1,
        "modelo": G.grafico_modelo(ctx),
        "matriz": G.grafico_matriz(mat),
        "familias_pit": G.grafico_familias(fam("pit", "Random forest"), "F1 «para»"),
        "familias_comp": G.grafico_familias(fam("comp", "Random forest"), "F1 macro"),
        "umbral": G.grafico_umbral(tabla_umbral, umbral),
        "imp_pit": G.grafico_importancia(pd.DataFrame(sel["importancia"]["pit"]), "Caída del F1"),
        "imp_comp": G.grafico_importancia(pd.DataFrame(sel["importancia"]["comp"]), "Caída del F1 macro"),
        "panorama": G.grafico_panorama(umbral),
        "carrera": G.grafico_carrera(umbral),
        "trayectoria": G.grafico_trayectoria(umbral),
        "prob_explora": G.grafico_probabilidades("prob_explora"),
        "prob_proba": G.grafico_probabilidades("prob_proba"),
        "puntaje": G.grafico_puntaje(umbral),
    }
    dist = pd.DataFrame(C["distancias"])
    dist["cercana"] = dist.categoria.isin(["1 vuelta", "2–3 vueltas", "4–10 vueltas"])
    dist["rotulo"] = [f"{num(f)} · {pct(q)}" for f, q in zip(dist.fp, dist.pct)]
    graficos["pr"] = G.grafico_pr(tabla_umbral, umbral, float(yp.mean()))
    graficos["distancias"] = G.grafico_distancias(dist)
    graficos["mdi_pit"] = G.grafico_mdi(pd.DataFrame(C["mdi"]["pit"]), "Importancia (MDI)")
    graficos["mdi_comp"] = G.grafico_mdi(pd.DataFrame(C["mdi"]["comp"]), "Importancia (MDI)")
    specs = {k: v.to_dict() for k, v in graficos.items()}

    # 7. Página ---------------------------------------------------------------------------------
    T = textos(d, info, res, L, h1, h4, sel, sistema, umbral, tabla_umbral, ctx, carreras, verificacion, paridad)
    T["prev_train"] = pct(float(yp.mean()), 1)
    u_f2 = A.umbral_f2(tabla_umbral)
    tu = tabla_umbral.set_index("umbral")
    T["f2"] = {"umbral": dec(u_f2), "f2_nuevo": dec(tu.loc[u_f2, "f2"], 4), "f2_base": dec(tu.loc[umbral, "f2"], 4),
               "coincide": abs(u_f2 - umbral) < 1e-9}
    T["corr"] = {
        "umbrales": [{"u": dec(f["umbral"]), "vp": num(f["vp"]), "fp": num(f["fp"]), "fn": num(f["fn"]),
                      "rec": pct(f["recall"], 1), "prec": pct(f["precision"], 1), "base": abs(f["umbral"] - umbral) < 1e-9}
                     for f in C["umbrales_2025"]],
        "cobertura": [{"k": f["k"], "n": num(f["paradas"]), "pct": pct(f["pct"], 1)} for f in C["cobertura"]],
        "fp_mediana": num(C["fp_mediana"]),
        "cercanas_pct": pct(sum(x["fp"] for x in C["distancias"][:3]) / C["fp_total"]),
        "mdi_pit": [x["variable"] for x in C["mdi"]["pit"][:4]], "mdi_comp": [x["variable"] for x in C["mdi"]["comp"][:4]],
    }
    u04 = next(f for f in C["umbrales_2025"] if abs(f["umbral"] - 0.40) < 1e-9)
    ub = next(f for f in C["umbrales_2025"] if abs(f["umbral"] - umbral) < 1e-9)
    T["corr"]["extra_vp"] = num(u04["vp"] - ub["vp"])
    T["corr"]["extra_fp"] = num(u04["fp"] - ub["fp"])
    entorno = jinja2.Environment(loader=jinja2.FileSystemLoader(DIR_APP), autoescape=False,
                                 undefined=jinja2.StrictUndefined)
    config_app["textos"] = {
        "aviso_alarma": f"La alarma marca una ventana, no la vuelta exacta: en 2025 solo el {T['test_prec']} de las "
                        "vueltas con alarma fue la vuelta de una parada.",
        "aviso_lluvia": f"Con lluvia el modelo casi no anticipa: en 2025 tuvo la alarma encendida en {T['ll_a']} de "
                        f"{T['ll_n']} paradas a neumáticos de lluvia.",
        "aviso_secado": "No ve cuándo se seca la pista: en Bélgica 2025, cuando el pelotón pasó de intermedios a seco, "
                        f"acertó el neumático en {T['belgica_ok']} de {T['belgica_n']} paradas.",
        "aviso_sc": "No sabe si hay safety car (quedó fuera del modelo): en 2025 tuvo la alarma encendida en "
                    f"{T['sc_a']} de {T['sc_n']} paradas con safety car.",
    }

    def incrustar(obj):  # JSON seguro dentro de <script type="application/json">
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    html = entorno.get_template("plantilla.html").render(T=T, specs=incrustar(specs), config=incrustar(config_app))
    (DIR_SITIO / "index.html").write_text(html, encoding="utf-8")
    for f in ["estilos.css", "app.js", "modelo.js"]:
        shutil.copyfile(DIR_APP / f, DIR_SITIO / f)
    shutil.copytree(DIR_APP / "img", DIR_SITIO / "img", dirs_exist_ok=True)
    (DIR_SITIO / ".nojekyll").write_text("", encoding="utf-8")

    construccion = {
        "fecha_construccion": dt.datetime.now().isoformat(timespec="seconds"),
        "versiones": {"python": sys.version.split()[0], "scikit-learn": sklearn.__version__, "pandas": pd.__version__,
                      "numpy": np.__version__, "altair": alt.__version__},
        "semilla": M.SEED, "umbral": umbral, "origen_paradas": d["origen_pits"],
        "comparacion_v6": verificacion, "paridad_navegador": paridad,
        "metricas_test": res, "sistema": sistema, "correcciones_e3": C,
        "umbral_regla_f2": A.umbral_f2(tabla_umbral),
    }
    (DIR_ART / "construccion.json").write_text(json.dumps(construccion, ensure_ascii=False, indent=1, default=float),
                                              encoding="utf-8")
    tam = sum(p.stat().st_size for p in DIR_SITIO.rglob("*") if p.is_file()) / 1e6
    log(f"Sitio generado en {DIR_SITIO.relative_to(RAIZ)} ({tam:.1f} MB) · artefactos en {DIR_ART.relative_to(RAIZ)}")
    if distintos or not all(p.get("verificado") for p in paridad.values()):
        log("Revisar: hay números que difieren de la v6 o la paridad del modelo no se verificó.")


def textos(d, info, res, L, h1, h4, sel, sistema, umbral, tabla_umbral, ctx, carreras, verificacion, paridad):
    """Todos los números que aparecen en la página, ya formateados."""
    pob, tr, te = d["poblacion"], d["train"], d["test"]
    seco, sc_, ll = (ctx.set_index("contexto").loc[c] for c in G.CONTEXTOS)
    reactivas_n = int(sc_.paradas + ll.paradas)
    reactivas_a = int(sc_.anticipadas + ll.anticipadas)
    h4s = pd.DataFrame(h4["seco"]).set_index(["situacion", "compuesto"]).pct
    perfil = L["perfil"]
    fpc = L["fp_categorias"]
    raw = d["raw"]
    pc = res["comp"]["por_clase"]
    u = tabla_umbral.set_index("umbral")
    fam_pit = {f["modelo"]: f for f in sel["familias"]["pit"]}
    fam_comp = {f["modelo"]: f for f in sel["familias"]["comp"]}
    grid_rf_none = [g for g in sel["grillas"]["pit"] if g["modelo"] == "Random forest" and g.get("class_weight") == "None"]
    abl = {k: {a["experimento"]: a for a in sel["ablacion"][k]} for k in ("pit", "comp")}
    T = {
        # Portada
        "pct_seco": pct(seco.pct), "seco_a": int(seco.anticipadas), "seco_n": int(seco.paradas),
        "pct_reactivas": pct(reactivas_a / reactivas_n), "reactivas_a": reactivas_a, "reactivas_n": reactivas_n,
        "pct_sc": pct(sc_.pct), "sc_a": int(sc_.anticipadas), "sc_n": int(sc_.paradas),
        "pct_ll": pct(ll.pct), "ll_a": int(ll.anticipadas), "ll_n": int(ll.paradas),
        "pct_episodios": pct(L["episodios_terminan_en_parada"]), "episodios": L["episodios"],
        "episodios_ok": int(round(L["episodios_terminan_en_parada"] * L["episodios"])),
        "episodio_mediana": num(L["episodio_mediana_vueltas"]),
        "acc_comp": pct(res["comp"]["modelo"]["accuracy"]), "acc_piso": pct(res["comp"]["piso"]["accuracy"]),
        # Datos
        "filas_silver": num(len(raw)), "cols_silver": raw.shape[1], "carreras_silver": raw.session_key.nunique(),
        "vueltas_sin_etiqueta": num(info["vueltas_sin_etiqueta"]), "carreras_sin_etiqueta": info["carreras_sin_etiqueta"],
        "vueltas_validas": num(info["vueltas_validas"]), "paradas_reales": num(info["paradas_reales"]),
        "carreras_validas": int(d["vueltas"].session_key.nunique()),
        "pct_paradas": pct(info["paradas_reales"] / info["vueltas_validas"], 1),
        "pilotos_corregidos": info["pilotos_corregidos"],
        "poblacion": num(len(pob)), "poblacion_paradas": num(int(pob.pit_stop.sum())),
        "sin_historia": num(info["vueltas_validas"] - len(pob)),
        "sin_historia_paradas": num(info["paradas_reales"] - int(pob.pit_stop.sum())),
        "train_v": num(len(tr)), "train_p": num(int(tr.pit_stop.sum())), "train_c": tr.session_key.nunique(),
        "test_v": num(len(te)), "test_p": num(int(te.pit_stop.sum())), "test_c": te.session_key.nunique(),
        "clases": {c: num(int((pob.objetivo_compuesto == c).sum())) for c in M.ORDEN},
        "clases_pct": {c: pct((pob.objetivo_compuesto == c).sum() / pob.pit_stop.sum()) for c in M.ORDEN},
        "fecha_desde": str(carreras.fecha.min())[:10], "fecha_hasta": str(carreras.fecha.max())[:10],
        "origen_pits": d["origen_pits"],
        # Hallazgo
        "h4_sin_hard": pct(h4s[("Sin safety car", "HARD")]), "h4_con_hard": pct(h4s[("Con safety car", "HARD")]),
        "h4_sin_soft": pct(h4s[("Sin safety car", "SOFT")]), "h4_con_soft": pct(h4s[("Con safety car", "SOFT")]),
        "h4_sin_med": pct(h4s[("Sin safety car", "MEDIUM")]), "h4_con_med": pct(h4s[("Con safety car", "MEDIUM")]),
        "h4_brecha": dec(h4["brecha_hard_seco"]),
        "h4_n_con": num(pd.DataFrame(h4["seco"]).query("situacion == 'Con safety car'").paradas.iloc[0]),
        "h4_n_sin": num(pd.DataFrame(h4["seco"]).query("situacion == 'Sin safety car'").paradas.iloc[0]),
        "h4_sc_total": num(h4["totales"]["con"]["paradas"]), "h4_sc_carreras": h4["totales"]["con"]["carreras"],
        "h4_lluvia_con": pct(h4["totales"]["con"]["pct_lluvia"], 1), "h4_lluvia_sin": pct(h4["totales"]["sin"]["pct_lluvia"], 1),
        **{k: (dec(v) if "sep" in k or "brecha" in k else (pct(v, 1) if "hard" in k else num(v, 2)))
           for k, v in A.hipotesis_2_y_4_originales(raw, d["raw_pits"]).items()},
        "h1_med_para": num(h1["resumen"]["para"]["mediana"]), "h1_med_sigue": num(h1["resumen"]["sigue"]["mediana"]),
        "h1_iqr_para": f"{num(h1['resumen']['para']['q1'])}–{num(h1['resumen']['para']['q3'])}",
        "h1_iqr_sigue": f"{num(h1['resumen']['sigue']['q1'])}–{num(h1['resumen']['sigue']['q3'])}",
        # Modelo
        "umbral": dec(umbral), "test_f1": dec(res["pit"]["modelo"]["f1"]),
        "test_prec": pct(res["pit"]["modelo"]["precision"], 1), "test_rec": pct(res["pit"]["modelo"]["recall"], 1),
        "test_alarmas": num(res["pit"]["modelo"]["alarmas"]), "test_siempre": dec(res["pit"]["siempre"]["f1"]), "test_siempre_prec": pct(res["pit"]["siempre"]["precision"], 1),
        "test_nunca_acc": pct(res["pit"]["nunca"]["accuracy"], 1), "test_acc": pct(res["pit"]["modelo"]["accuracy"], 1),
        "matriz_pit": res["pit"]["matriz"], "test_vp": num(res["pit"]["matriz"][1][1]),
        "test_fn": num(res["pit"]["matriz"][1][0]), "test_fp": num(res["pit"]["matriz"][0][1]),
        "comp_f1": dec(res["comp"]["modelo"]["f1_macro"]), "comp_piso_f1": dec(res["comp"]["piso"]["f1_macro"]),
        "comp_bacc": pct(res["comp"]["modelo"]["accuracy_balanceada"], 1),
        "por_clase": {c: {"p": pct(pc[c]["precision"]), "r": pct(pc[c]["recall"]), "f": dec(pc[c]["f1-score"], 2),
                          "n": int(pc[c]["support"])} for c in M.ORDEN},
        "cv_pit": dec(sel["elegidos_cv"][0]["f1_validacion"]), "cv_pit_sd": dec(sel["elegidos_cv"][0]["desvio"]),
        "cv_pit_tr": dec(sel["elegidos_cv"][0]["f1_entrenamiento"]),
        "cv_comp": dec(sel["elegidos_cv"][1]["f1_validacion"]), "cv_comp_sd": dec(sel["elegidos_cv"][1]["desvio"]),
        "cv_comp_tr": dec(sel["elegidos_cv"][1]["f1_entrenamiento"]),
        "piso_siempre_cv": dec(fam_pit["Piso siempre parar"]["f1_validacion"]),
        "piso_hard_cv": dec(fam_comp["Piso mayoría (siempre HARD)"]["f1_validacion"]),
        "piso_azar_cv": dec(fam_comp["Piso estratificado (al azar)"]["f1_validacion"]),
        "par_pit": f"{'+' if sel['pareada']['pit']['diferencia_media'] >= 0 else ''}{dec(sel['pareada']['pit']['diferencia_media'])} ± {dec(sel['pareada']['pit']['diferencia_desvio'])}",
        "par_comp": f"{'+' if sel['pareada']['comp']['diferencia_media'] >= 0 else ''}{dec(sel['pareada']['comp']['diferencia_media'])} ± {dec(sel['pareada']['comp']['diferencia_desvio'])}",
        "par_pit_folds": sel["pareada"]["pit"]["folds_gana_bosque"], "par_comp_folds": sel["pareada"]["comp"]["folds_gana_bosque"],
        "par_folds": sel["pareada"]["pit"]["folds"],
        "log_pit": dec(sel["pareada"]["pit"]["medias"]["Regresión logística"]),
        "log_comp": dec(sel["pareada"]["comp"]["medias"]["Regresión logística"]),
        "log_pit_c": num(sel["pareada"]["pit"]["mejores_parametros"]["Regresión logística"]["C"], 3),
        "log_comp_c": num(sel["pareada"]["comp"]["mejores_parametros"]["Regresión logística"]["C"], 4),
        "rf_sin_pesos": dec(grid_rf_none[0]["f1_validacion"]) if grid_rf_none else "—",
        "azar_pit": dec(sel["azar"][0]["al_azar"]), "azar_comp": dec(sel["azar"][1]["al_azar"]),
        "abl_pit_sd": dec(abl["pit"]["Todas las variables"]["desvio"]),
        "abl_comp_sd": dec(abl["comp"]["Todas las variables"]["desvio"]),
        "abl_comp_peloton": dec(abl["comp"]["Sin pelotón (field_*_prev)"]["diferencia"]),
        "abl_comp_lap": dec(abl["comp"]["Sin lap_number"]["diferencia"]),
        "abl_pit_lap": dec(abl["pit"]["Sin lap_number"]["diferencia"]),
        "u_f1": dec(u.loc[umbral, "f1"], 4), "u_prec": pct(u.loc[umbral, "precision"], 1),
        "u_rec": pct(u.loc[umbral, "recall"], 1), "u055_f1": dec(u.loc[0.55, "f1"], 4),
        "u055_prec": pct(u.loc[0.55, "precision"], 1), "u055_rec": pct(u.loc[0.55, "recall"], 1),
        "fp_13": num(fpc.get("adelantada 1-3 vueltas", 0)), "fp_410": num(fpc.get("adelantada 4-10 vueltas", 0)),
        "fp_sin": num(fpc.get("sin parada en las 10 vueltas siguientes", 0)),
        "fp_13_pct": pct(fpc.get("adelantada 1-3 vueltas", 0) / L["fp_total"], 1),
        "fp_410_pct": pct(fpc.get("adelantada 4-10 vueltas", 0) / L["fp_total"], 1),
        "fp_sin_pct": pct(fpc.get("sin parada en las 10 vueltas siguientes", 0) / L["fp_total"], 1),
        "fp_no_vuelve": pct(L["fp_sin_cercana_no_vuelve_a_parar"], 1),
        "perfil": {t: {k: (pct(v, 1) if k.startswith("pct") else num(v)) for k, v in p.items()} for t, p in perfil.items()},
        "alarma_exacta": pct(L["alarma_exacta"], 1), "alarma_ventana": pct(L["alarma_ventana_3"], 1),
        "comp_entrada": {k: pct(v["acierto"]) for k, v in L["comp_por_compuesto_entrada"].items()},
        "comp_peores": [{"carrera": NOMBRES_ES.get(c["carrera"], c["carrera"]), "acierto": pct(c["acierto"]),
                         "paradas": c["paradas"]} for c in L["comp_peores_carreras"]],
        "comp_errores": L["comp_errores"],
        "belgica_n": L["belgica"]["paradas"], "belgica_ok": L["belgica"]["aciertos"],
        "sis_ambas": num(sistema["ambas"]), "sis_paradas": num(sistema["paradas"]),
        "sis_pct": pct(sistema["ambas"] / sistema["paradas"], 1),
        "sis_comp_det": pct(sistema["ambas"] / sistema["detectadas"], 1), "sis_hard": num(sistema["hard_ok"]),
        "sis_prec": pct(sistema["ambas"] / sistema["alarmas"], 1),
        "ejemplo": L["ejemplo_racha"] | {"carrera": NOMBRES_ES.get(L["ejemplo_racha"]["carrera"], L["ejemplo_racha"]["carrera"])},
        "familias": {k: [{"modelo": f["modelo"], "media": dec(f["f1_validacion"]), "desvio": dec(f["desvio"]),
                          "train": dec(f["f1_entrenamiento"]), "elegido": f["modelo"] == "Random forest"}
                         for f in sel["familias"][k]] for k in ("pit", "comp")},
        "imp_pit": [dict(i, caida_t=dec(i["caida"], 3)) for i in sel["importancia"]["pit"][:4]],
        "imp_comp": [dict(i, caida_t=dec(i["caida"], 3)) for i in sel["importancia"]["comp"][:4]],
        # Reproducibilidad
        "verificacion": verificacion, "paridad": paridad,
        "n_verif_ok": sum(f["coincide"] for f in verificacion), "n_verif": len(verificacion),
        "sklearn": sklearn.__version__, "fecha_build": dt.date.today().isoformat(),
        "max_dif": "{:.0e}".format(max(p.get("max_diferencia", 0) for p in paridad.values())) if all(
            "max_diferencia" in p for p in paridad.values()) else "—",
    }
    return T


if __name__ == "__main__":
    main()
