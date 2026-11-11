"""Recalcula la selección de modelos de la v6 (secciones 4, 5, 6, 8 y 11).

Es la parte costosa (unos minutos): comparación de familias, grillas, comparación
pareada repetida, ablación, pedazos al azar e importancia por permutación. El
código es el de ``Entrega3/Entrega3_F1_v6.ipynb`` con las mismas semillas y
pedazos. ``build_app.py --seleccion`` lo ejecuta y guarda el resultado en
``Entrega4/artefactos/seleccion_v6.json``; sin esa opción se reutiliza el JSON.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_validate
from sklearn.tree import DecisionTreeClassifier

from src import modelo as m

SEED = m.SEED


def _familias(objetivo):
    pisos = ({"Piso mayoría (nunca parar)": DummyClassifier(strategy="most_frequent"),
              "Piso siempre parar": DummyClassifier(strategy="constant", constant=1)}
             if objetivo == "pit" else
             {"Piso mayoría (siempre HARD)": DummyClassifier(strategy="most_frequent"),
              "Piso estratificado (al azar)": DummyClassifier(strategy="stratified", random_state=SEED)})
    return {**pisos,
            "Regresión logística": LogisticRegression(max_iter=3000, class_weight="balanced", random_state=SEED),
            "Árbol": DecisionTreeClassifier(max_depth=8, min_samples_leaf=20, class_weight="balanced", random_state=SEED),
            "Random forest": RandomForestClassifier(n_estimators=120, max_depth=12, min_samples_leaf=15,
                                                    class_weight="balanced_subsample", random_state=SEED, n_jobs=-1),
            "HistGradientBoosting": HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=15,
                                                                   class_weight="balanced", random_state=SEED)}


def comparar(X, y, cv, metrica, objetivo, registro):
    filas = []
    for nombre, estimador in _familias(objetivo).items():
        r = cross_validate(m.pipeline(estimador, registro), X, y, cv=cv, scoring=metrica, n_jobs=1,
                           return_train_score=True, error_score="raise")
        filas.append({"modelo": nombre, "f1_validacion": float(r["test_score"].mean()),
                      "desvio": float(r["test_score"].std(ddof=0)), "f1_entrenamiento": float(r["train_score"].mean()),
                      "folds": [float(v) for v in r["test_score"]]})
    return sorted(filas, key=lambda f: -f["f1_validacion"])


def ajustar_finalistas(X, y, cv, score, registro):
    grids = {
        "Regresión logística": (LogisticRegression(max_iter=5000, random_state=SEED),
                                {"modelo__C": [0.0001, 0.0003, 0.001, 0.003, 0.03, 0.3, 3],
                                 "modelo__class_weight": [None, "balanced"]}),
        "Random forest": (RandomForestClassifier(n_estimators=150, random_state=SEED, n_jobs=-1),
                          [{"modelo__max_depth": [8, 12, 16], "modelo__min_samples_leaf": [10, 25, 60],
                            "modelo__class_weight": ["balanced_subsample"]},
                           {"modelo__max_depth": [16], "modelo__min_samples_leaf": [25],
                            "modelo__class_weight": [None]}])}
    encontrados, filas = {}, []
    for nombre, (modelo, parametros) in grids.items():
        grid = GridSearchCV(m.pipeline(modelo, registro), parametros, scoring=score, cv=cv, n_jobs=1, refit=True,
                            return_train_score=True, error_score="raise")
        grid.fit(X, y)
        encontrados[nombre] = grid
        t = pd.DataFrame(grid.cv_results_)
        for i, params in enumerate(t["params"]):
            filas.append({"modelo": nombre,
                          **{k.replace("modelo__", ""): (v if v is not None else "None") for k, v in params.items()},
                          "f1_validacion": float(t.mean_test_score[i]), "desvio": float(t.std_test_score[i]),
                          "f1_entrenamiento": float(t.mean_train_score[i]), "rank": int(t.rank_test_score[i])})
    return encontrados, filas


def repetir_y_elegir(grids, X, y, g, score, carreras_train):
    puntajes = {k: [] for k in grids}
    for rep in range(3):
        cv = m.cv_por_carrera(g, carreras_train, seed=SEED + rep)
        for nombre, grid in grids.items():
            valores = cross_validate(clone(grid.best_estimator_), X, y, cv=cv, scoring=score,
                                     n_jobs=1, error_score="raise")["test_score"]
            puntajes[nombre].extend(valores.tolist())
    t = pd.DataFrame(puntajes)
    d = t["Random forest"] - t["Regresión logística"]
    elegido = "Random forest" if d.mean() > max(0, d.std(ddof=0)) else "Regresión logística"
    return {"medias": {k: float(t[k].mean()) for k in t}, "desvios": {k: float(t[k].std(ddof=0)) for k in t},
            "diferencia_media": float(d.mean()), "diferencia_desvio": float(d.std(ddof=0)),
            "folds_gana_bosque": int((d > 0).sum()), "folds": int(len(d)), "elegido": elegido,
            "mejores_parametros": {k: {p.replace("modelo__", ""): v for p, v in grids[k].best_params_.items()}
                                   for k in grids}}


GRUPOS_ABLACION = {
    "tyre_age_prev": ["tyre_age_prev"], "compound_prev": ["compound_prev"],
    "position_prev": ["position_prev"], "stops_before": ["stops_before"],
    "used_* (compuestos ya usados)": ["used_soft", "used_medium", "used_hard"],
    "pelotón (field_*_prev)": ["field_soft_prev", "field_medium_prev", "field_hard_prev", "field_lluvia_prev"],
    "clima (temperaturas, humedad, lluvia)": ["track_temperature_prev", "air_temperature_prev", "humidity_prev", "rainfall_prev"],
    "circuito y equipo": ["circuit_short_name", "team_name"],
    "lap_number": ["lap_number"]}


def ablar(modelo, X, y, cv, scoring):
    base = cross_validate(clone(modelo), X, y, cv=cv, scoring=scoring)["test_score"]
    filas = [{"experimento": "Todas las variables", "f1": float(base.mean()), "desvio": float(base.std(ddof=0)),
              "diferencia": 0.0}]
    for nombre, cols in GRUPOS_ABLACION.items():
        est = clone(modelo)
        est.steps[1] = ("preparar", m.pipeline(None, None, [c for c in m.NUM if c not in cols],
                                               [c for c in m.CAT if c not in cols]).steps[1][1])
        r = cross_validate(est, X, y, cv=cv, scoring=scoring)["test_score"]
        filas.append({"experimento": f"Sin {nombre}", "f1": float(r.mean()), "desvio": float(r.std(ddof=0)),
                      "diferencia": float(r.mean() - base.mean())})
    return filas


def importancia_validacion(modelo, X, y, cv, scoring):
    resultados = []
    for tr, va in cv.split():
        est = clone(modelo).fit(X.iloc[tr], y.iloc[tr])
        Xva = est[:1].transform(X.iloc[va])
        p = permutation_importance(est[1:], Xva, y.iloc[va], scoring=scoring, n_repeats=3,
                                   random_state=SEED, n_jobs=1)
        resultados.append(p.importances_mean)
    t = pd.DataFrame(resultados, columns=m.FEATURES)
    return [{"variable": c, "caida": float(t[c].mean()), "desvio": float(t[c].std(ddof=0)),
             "folds_positivos": int((t[c] > 0).sum())} for c in t.mean().sort_values(ascending=False).index]


def calcular(d: dict, log=print) -> dict:
    reg, tr, ct = d["registro"], d["train"], d["carreras_train"]
    Xp, yp, gp = m.split_datos(tr)
    Xc, yc, gc = m.split_datos(tr, True)
    cvp, cvc = m.cv_por_carrera(gp, ct), m.cv_por_carrera(gc, ct)
    out = {}
    log("  familias…")
    out["familias"] = {"pit": comparar(Xp, yp, cvp, "f1", "pit", reg),
                       "comp": comparar(Xc, yc, cvc, "f1_macro", "comp", reg)}
    log("  grillas…")
    gpit, out_gpit = ajustar_finalistas(Xp, yp, cvp, "f1", reg)
    gcomp, out_gcomp = ajustar_finalistas(Xc, yc, cvc, "f1_macro", reg)
    out["grillas"] = {"pit": out_gpit, "comp": out_gcomp}
    log("  comparación pareada…")
    out["pareada"] = {"pit": repetir_y_elegir(gpit, Xp, yp, gp, "f1", ct),
                      "comp": repetir_y_elegir(gcomp, Xc, yc, gc, "f1_macro", ct)}
    mod_pit = gpit[out["pareada"]["pit"]["elegido"]].best_estimator_
    mod_comp = gcomp[out["pareada"]["comp"]["elegido"]].best_estimator_
    sobre = []
    for nombre, mo, X, y, cv, sc in [("pit_stop", mod_pit, Xp, yp, cvp, "f1"),
                                     ("new_compound", mod_comp, Xc, yc, cvc, "f1_macro")]:
        r = cross_validate(clone(mo), X, y, cv=cv, scoring=sc, return_train_score=True)
        sobre.append({"etapa": nombre, "f1_entrenamiento": float(r["train_score"].mean()),
                      "f1_validacion": float(r["test_score"].mean()), "desvio": float(r["test_score"].std(ddof=0)),
                      "folds": [float(v) for v in r["test_score"]]})
    out["elegidos_cv"] = sobre
    log("  ablación…")
    out["ablacion"] = {"pit": ablar(mod_pit, Xp, yp, cvp, "f1"), "comp": ablar(mod_comp, Xc, yc, cvc, "f1_macro")}
    log("  pedazos al azar…")
    azar = []
    for etapa, mo, X, y, cv, sc in [("pit_stop", mod_pit, Xp, yp, cvp, "f1"),
                                    ("new_compound", mod_comp, Xc, yc, cvc, "f1_macro")]:
        por_carrera = cross_validate(clone(mo), X, y, cv=cv, scoring=sc)["test_score"]
        al_azar = cross_validate(clone(mo), X, y, scoring=sc,
                                 cv=StratifiedKFold(n_splits=m.N_FOLDS, shuffle=True, random_state=SEED))["test_score"]
        azar.append({"etapa": etapa, "por_carrera": float(por_carrera.mean()), "al_azar": float(al_azar.mean())})
    out["azar"] = azar
    log("  importancia por permutación…")
    out["importancia"] = {"pit": importancia_validacion(mod_pit, Xp, yp, cvp, "f1"),
                          "comp": importancia_validacion(mod_comp, Xc, yc, cvc, "f1_macro")}
    return out
