"""Modelo de la Entrega 3 (v6) como módulo importable.

Este módulo traslada, sin cambiar su lógica, el código de
``Entrega3/Entrega3_F1_v6.ipynb`` que hace falta para entrenar y usar los dos
modelos elegidos:

* la limpieza del dato de origen (sección 1 del notebook),
* ``RegistroCarreras`` e ``HistoriaCausal`` (sección 2),
* la población que se predice y la partición 2023-2024 / 2025 (secciones 2 y 3),
* los pedazos de validación por carrera (sección 3.1),
* el pipeline y los hiperparámetros elegidos (secciones 5 y 6).

Al estar en un módulo, los ``.joblib`` guardados por ``build_app.py`` se pueden
cargar desde la aplicación (pendiente 3 de ``Entrega4/PENDIENTES.md``).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.model_selection import PredefinedSplit, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.silver_pipeline import resolve_driver_pits

# --------------------------------------------------------------------------
# Constantes (idénticas a la v6)
# --------------------------------------------------------------------------
SEED = 42
ORDEN = ["SOFT", "MEDIUM", "HARD", "LLUVIA"]
CLAVE = ["session_key", "driver_number", "lap_number"]
COMPUESTOS_SECO = ["SOFT", "MEDIUM", "HARD"]
N_FOLDS = 4
UMBRAL_V6 = 0.475  # umbral elegido en la v6 (máximo F1 OOF) y confirmado en la v7 (máximo F2 OOF)

FILAS_ESPERADAS = {"f1_silver_dataset": 77373, "f1_silver_pit_stops": 2333}
COLUMNAS_ESPERADAS = {"f1_silver_dataset": 89, "f1_silver_pit_stops": 93}

NUM = ["lap_number", "tyre_age_prev", "position_prev", "stops_before", "track_temperature_prev",
       "air_temperature_prev", "humidity_prev", "used_soft", "used_medium", "used_hard",
       "field_soft_prev", "field_medium_prev", "field_hard_prev", "field_lluvia_prev"]
CAT = ["compound_prev", "circuit_short_name", "team_name", "rainfall_prev"]
FEATURES = NUM + CAT
PROHIBIDAS = {"pit_stop", "new_compound", "current_compound", "stint_number", "pit_duration",
              "lane_duration", "stop_duration", "session_max_lap_observed", "lap_duration",
              "gap_to_leader_raw", "safety_car_active", "yellow_flag_active", "interval_raw"}
assert not (set(FEATURES) & PROHIBIDAS)
COLS_X = CLAVE + ["circuit_short_name", "team_name"]
DESCRIPTIVAS = ["season", "meeting_name", "full_name", "pit_stop", "safety_car_active"]

RAIZ = Path(__file__).resolve().parents[1]
DIR_SILVER = RAIZ / "include" / "output" / "silver"
DIR_BRONZE = RAIZ / "include" / "output" / "bronze"


# --------------------------------------------------------------------------
# Carga de datos
# --------------------------------------------------------------------------
def cargar_vueltas(dir_silver: Path = DIR_SILVER) -> pd.DataFrame:
    """Lee el CSV Silver de vueltas producido por el pipeline y valida su forma."""
    ruta = dir_silver / "f1_silver_dataset.csv"
    raw = pd.read_csv(ruta, low_memory=False)
    esperado = (FILAS_ESPERADAS["f1_silver_dataset"], COLUMNAS_ESPERADAS["f1_silver_dataset"])
    if raw.shape != esperado:
        raise ValueError(f"{ruta} tiene forma {raw.shape}; la v6 usa {esperado}.")
    assert raw.duplicated(CLAVE).sum() == 0, "Existen vueltas duplicadas."
    return raw


def reconstruir_paradas_desde_bronce(raw: pd.DataFrame, dir_bronze: Path = DIR_BRONZE) -> pd.DataFrame:
    """Arma el dataset de paradas con la misma lógica que la v6 (celda 3).

    La v6 bajaba ``pit`` y ``stints`` de la API de OpenF1. Acá se leen los mismos
    endpoints desde la capa Bronce del pipeline y se emparejan con
    ``resolve_driver_pits`` de ``src/silver_pipeline.py`` (la función original).
    """
    vueltas_idx = {(r["session_key"], r["driver_number"], r["lap_number"]): r
                   for r in raw.to_dict("records")}
    con_pits = raw.loc[raw["pit_data_available"] == True, ["season", "session_key"]].drop_duplicates()  # noqa: E712
    salida = []
    for season, sk in sorted(con_pits.itertuples(index=False, name=None), key=lambda t: t[1]):
        carpeta = dir_bronze / f"season={season}" / f"session={sk}"
        pits = json.loads((carpeta / "pit.json").read_text(encoding="utf-8"))
        stints = json.loads((carpeta / "stints.json").read_text(encoding="utf-8"))
        pits_por_piloto, stints_por_piloto = {}, {}
        for p in pits:
            pits_por_piloto.setdefault(p["driver_number"], []).append(p)
        for s in stints:
            stints_por_piloto.setdefault(s["driver_number"], []).append(s)
        for piloto, pits_piloto in pits_por_piloto.items():
            detalle = resolve_driver_pits(pits_piloto, stints_por_piloto.get(piloto, []))
            for vuelta, det in detalle.items():
                clave = (sk, piloto, vuelta)
                if clave not in vueltas_idx:
                    continue
                fila = dict(vueltas_idx[clave])
                fila["pit_stop_number"] = det["pit_stop_number"]
                for col_det, col_fila in [("current_compound", "current_compound"),
                                          ("stint_in_number", "stint_number"),
                                          ("tyre_age_at_start", "tyre_age_at_start")]:
                    if det[col_det] is not None:
                        fila[col_fila] = det[col_det]
                fila["new_stint_number"] = det["new_stint_number"]
                fila["new_compound"] = det["new_compound"]
                fila["new_tyre_age_at_start"] = det["new_tyre_age_at_start"]
                fila["pit_stop"] = True
                salida.append(fila)
    return pd.DataFrame(salida).drop_duplicates(CLAVE, keep="last")


def cargar_paradas(raw: pd.DataFrame, dir_silver: Path = DIR_SILVER,
                   dir_bronze: Path = DIR_BRONZE) -> tuple[pd.DataFrame, str]:
    """Usa ``f1_silver_pit_stops.csv`` del pipeline si existe; si no, lo reconstruye desde Bronce."""
    ruta = dir_silver / "f1_silver_pit_stops.csv"
    if ruta.exists():
        pits = pd.read_csv(ruta, low_memory=False)
        origen = str(ruta.relative_to(RAIZ))
    else:
        pits = reconstruir_paradas_desde_bronce(raw, dir_bronze)
        origen = "reconstruido desde include/output/bronze (pit.json + stints.json)"
    if len(pits) != FILAS_ESPERADAS["f1_silver_pit_stops"]:
        raise ValueError(f"Paradas: {len(pits)} filas; la v6 usa {FILAS_ESPERADAS['f1_silver_pit_stops']}.")
    assert pits.duplicated(CLAVE).sum() == 0, "Existen paradas duplicadas."
    assert set(pits.session_key.dropna()).issubset(set(raw.session_key.dropna()))
    return pits, origen


# --------------------------------------------------------------------------
# Limpieza del dato de origen (v6, celda 6)
# --------------------------------------------------------------------------
def limpiar_vueltas(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Descarta vueltas sin etiqueta y corrige el stint mal cargado de Bélgica 2025."""
    vueltas = raw.loc[raw["pit_stop"].notna()].copy()
    vueltas["pit_stop"] = vueltas["pit_stop"].astype(str).str.lower().eq("true") | (vueltas["pit_stop"] == 1)
    vueltas["season"] = pd.to_numeric(vueltas["season"], errors="raise").astype(int)
    vueltas = vueltas.sort_values(CLAVE).reset_index(drop=True)

    stints = (vueltas.groupby(["session_key", "driver_number", "stint_number"], dropna=False)
              .agg(primera=("lap_number", "min"), ultima=("lap_number", "max"),
                   compuesto=("current_compound", "first")).reset_index())
    s1 = stints[(stints.stint_number == 1) & (stints.ultima == 1)]
    s2 = stints[(stints.stint_number == 2) & (stints.primera == 2)]
    candidatos = s1.merge(s2, on=["session_key", "driver_number"], suffixes=("_1", "_2"))
    paradas_1_2 = (vueltas.loc[vueltas.pit_stop & vueltas.lap_number.le(2)]
                   .groupby(["session_key", "driver_number"]).size())
    candidatos["parada_temprana"] = candidatos.set_index(["session_key", "driver_number"]).index.map(paradas_1_2).fillna(0)
    corregir = candidatos.loc[candidatos.compuesto_1.ne(candidatos.compuesto_2) & candidatos.parada_temprana.eq(0),
                              ["session_key", "driver_number", "compuesto_1"]].copy()
    if len(corregir):
        clave_corr = corregir.set_index(["session_key", "driver_number"])["compuesto_1"]
        idx = pd.MultiIndex.from_frame(vueltas[["session_key", "driver_number"]])
        previo = pd.Series(idx.map(clave_corr), index=vueltas.index)
        mask = previo.notna() & vueltas.stint_number.eq(2)
        vueltas.loc[mask, "current_compound"] = previo[mask]
    info = {"pilotos_corregidos": int(len(corregir)),
            "vueltas_sin_etiqueta": int(raw["pit_stop"].isna().sum()),
            "carreras_sin_etiqueta": int(raw.loc[raw["pit_stop"].isna(), "session_key"].nunique()),
            "vueltas_validas": int(len(vueltas)),
            "paradas_reales": int(vueltas.pit_stop.sum())}
    return vueltas, info


# --------------------------------------------------------------------------
# Variables históricas dentro del pipeline (v6, sección 2)
# --------------------------------------------------------------------------
class RegistroCarreras:
    """Registro de vueltas por carrera, como lo tendría la app durante la carrera.

    Guarda el estado ya calculado de cada carrera para no recalcularlo en cada fold.
    Al clonar el pipeline se comparte el mismo registro (no se copia).
    """
    COLUMNAS = ["session_key", "driver_number", "lap_number", "pit_stop", "current_compound",
                "tyre_age", "position", "rainfall", "track_temperature", "air_temperature", "humidity"]

    def __init__(self, vueltas):
        self.vueltas = vueltas[self.COLUMNAS].sort_values(CLAVE).reset_index(drop=True)
        self._piloto, self._peloton = {}, {}

    def __deepcopy__(self, memo):
        return self

    def estado(self, carreras):
        faltan = [c for c in pd.unique(carreras) if c not in self._piloto]
        if faltan:
            v = self.vueltas[self.vueltas.session_key.isin(faltan)].copy()
            gp = v.groupby(["session_key", "driver_number"], sort=False)
            # Estado del piloto AL TERMINAR cada vuelta; se usa recién en una vuelta posterior.
            piloto = v[CLAVE].copy()
            for col, nueva in {"current_compound": "compound_prev", "tyre_age": "tyre_age_prev",
                               "position": "position_prev", "rainfall": "rainfall_prev",
                               "track_temperature": "track_temperature_prev",
                               "air_temperature": "air_temperature_prev", "humidity": "humidity_prev"}.items():
                piloto[nueva] = v[col]
            piloto["stops_before"] = gp["pit_stop"].cumsum().astype(int)
            for c in COMPUESTOS_SECO:
                piloto[f"used_{c.lower()}"] = (v.current_compound.eq(c).astype(float)
                                               .groupby([v.session_key, v.driver_number]).cummax())
            # Proporción del pelotón en cada compuesto al terminar cada vuelta.
            frac = pd.crosstab([v.session_key, v.lap_number], v.current_compound, normalize="index")
            for c in COMPUESTOS_SECO + ["INTERMEDIATE", "WET"]:
                if c not in frac.columns:
                    frac[c] = 0.0
            frac["LLUVIA"] = frac["INTERMEDIATE"] + frac["WET"]
            frac = (frac[COMPUESTOS_SECO + ["LLUVIA"]]
                    .rename(columns=lambda c: f"field_{c.lower()}_prev").reset_index())
            for c in faltan:
                self._piloto[c] = piloto[piloto.session_key.eq(c)]
                self._peloton[c] = frac[frac.session_key.eq(c)]
        lista = list(pd.unique(carreras))
        return (pd.concat([self._piloto[c] for c in lista], ignore_index=True),
                pd.concat([self._peloton[c] for c in lista], ignore_index=True))


class HistoriaCausal(BaseEstimator, TransformerMixin):
    """Primer paso del pipeline: arma las variables históricas de cada vuelta a decidir.

    Del registro lee SOLO vueltas anteriores de la misma carrera: la última vuelta previa
    del piloto y la vuelta t-1 del pelotón. fit no aprende nada (no hay estadísticas del dataset).
    """

    def __init__(self, registro=None):
        self.registro = registro

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        piloto, peloton = self.registro.estado(X["session_key"])
        base = X[COLS_X].copy()
        base["_orden"] = np.arange(len(base))
        base["lap_number"] = base["lap_number"].astype("int64")
        piloto = piloto.astype({"lap_number": "int64"}).sort_values("lap_number")
        # allow_exact_matches=False: la última vuelta del piloto ESTRICTAMENTE anterior a la que se decide.
        salida = pd.merge_asof(base.sort_values("lap_number"), piloto, on="lap_number",
                               by=["session_key", "driver_number"],
                               allow_exact_matches=False, direction="backward")
        peloton = peloton.assign(lap_number=peloton.lap_number.astype("int64") + 1)
        salida = salida.merge(peloton, on=["session_key", "lap_number"], how="left")
        salida = salida.sort_values("_orden").reset_index(drop=True)
        salida["stops_before"] = salida["stops_before"].fillna(0)
        for c in COMPUESTOS_SECO:
            salida[f"used_{c.lower()}"] = salida[f"used_{c.lower()}"].fillna(0.0)
        salida.index = X.index
        return salida[FEATURES]


# --------------------------------------------------------------------------
# Población, partición y validación (v6, secciones 2, 3 y 3.1)
# --------------------------------------------------------------------------
def armar_poblacion(vueltas: pd.DataFrame, raw_pits: pd.DataFrame) -> pd.DataFrame:
    """Vueltas con al menos una vuelta previa del piloto con compuesto y edad conocidos."""
    gpv = vueltas.groupby(["session_key", "driver_number"], sort=False)
    tiene_historia = gpv["current_compound"].shift(1).notna() & gpv["tyre_age"].shift(1).notna()
    poblacion = vueltas.loc[tiene_historia, COLS_X + DESCRIPTIVAS].reset_index(drop=True)
    objetivos = raw_pits[CLAVE + ["new_compound"]].copy()
    objetivos["objetivo_compuesto"] = objetivos["new_compound"].replace({"INTERMEDIATE": "LLUVIA", "WET": "LLUVIA"})
    poblacion = poblacion.merge(objetivos[CLAVE + ["objetivo_compuesto"]], on=CLAVE, how="left",
                                validate="one_to_one")
    assert poblacion.loc[poblacion.pit_stop, "objetivo_compuesto"].isin(ORDEN).all(), "Paradas sin compuesto."
    return poblacion


def pipeline(modelo, registro=None, nums=NUM, cats=CAT) -> Pipeline:
    preparar = ColumnTransformer([
        ("num", Pipeline([("imputar", SimpleImputer(strategy="median")),
                          ("escalar", StandardScaler())]), list(nums)),
        ("cat", Pipeline([("imputar", SimpleImputer(strategy="most_frequent")),
                          ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), list(cats))])
    return Pipeline([("historia", HistoriaCausal(registro)), ("preparar", preparar), ("modelo", modelo)])


def bosque_elegido() -> RandomForestClassifier:
    """Hiperparámetros elegidos en la v6 para los dos pasos (GridSearchCV, sección 5)."""
    return RandomForestClassifier(n_estimators=150, max_depth=12, min_samples_leaf=10,
                                  class_weight="balanced_subsample", random_state=SEED, n_jobs=-1)


def split_datos(tabla: pd.DataFrame, solo_pits: bool = False):
    v = tabla.loc[tabla.pit_stop].reset_index(drop=True) if solo_pits else tabla
    y = v.objetivo_compuesto if solo_pits else v.pit_stop.astype(int)
    return v[COLS_X].copy(), y, v.session_key


def carreras_entrenamiento(train: pd.DataFrame) -> pd.DataFrame:
    return (train.groupby("session_key")
            .agg(lluvia=("objetivo_compuesto", lambda s: s.eq("LLUVIA").any()),
                 meeting_name=("meeting_name", "first"), season=("season", "first")).reset_index())


def folds_por_carrera(carreras_train: pd.DataFrame, seed: int = SEED) -> pd.Series:
    """4 pedazos de carreras enteras, estratificando las carreras por 'tuvo paradas a LLUVIA'."""
    asignacion = pd.Series(-1, index=carreras_train.session_key)
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    for i, (_, b) in enumerate(skf.split(carreras_train, carreras_train.lluvia)):
        asignacion.iloc[b] = i
    return asignacion


def cv_por_carrera(grupos: pd.Series, carreras_train: pd.DataFrame, seed: int = SEED) -> PredefinedSplit:
    return PredefinedSplit(grupos.map(folds_por_carrera(carreras_train, seed)).values)


def preparar_todo(dir_silver: Path = DIR_SILVER, dir_bronze: Path = DIR_BRONZE) -> dict:
    """Ejecuta la preparación completa de la v6 y devuelve todo lo necesario para modelar."""
    raw = cargar_vueltas(dir_silver)
    raw_pits, origen_pits = cargar_paradas(raw, dir_silver, dir_bronze)
    vueltas, info = limpiar_vueltas(raw)
    registro = RegistroCarreras(vueltas)
    poblacion = armar_poblacion(vueltas, raw_pits)
    train = poblacion[poblacion.season.lt(2025)].reset_index(drop=True)
    test = poblacion[poblacion.season.eq(2025)].reset_index(drop=True)
    assert set(train.session_key).isdisjoint(set(test.session_key))
    return {"raw": raw, "raw_pits": raw_pits, "origen_pits": origen_pits, "vueltas": vueltas,
            "info_limpieza": info, "registro": registro, "poblacion": poblacion,
            "train": train, "test": test, "carreras_train": carreras_entrenamiento(train)}
