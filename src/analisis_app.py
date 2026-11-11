"""Números y tablas de la aplicación de la Entrega 4.

Todo sale de los datos del pipeline y de los modelos de ``src/modelo.py``. El
código de evaluación replica las celdas 40, 48, 51, 53, 59 y 60 de
``Entrega3/Entrega3_F1_v6.ipynb``; lo nuevo para la app (predicciones fuera de
fold de 2023-2024 y tipos de parada) se marca como tal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, fbeta_score, balanced_accuracy_score, classification_report,
                             confusion_matrix, f1_score, precision_score, recall_score)

from src import modelo as m


# --------------------------------------------------------------------------
# Entrenamiento final y predicciones fuera de muestra
# --------------------------------------------------------------------------
def entrenar_finales(d: dict):
    reg, tr = d["registro"], d["train"]
    Xp, yp, _ = m.split_datos(tr)
    Xc, yc, _ = m.split_datos(tr, True)
    mod_pit = m.pipeline(m.bosque_elegido(), reg).fit(Xp, yp)
    mod_comp = m.pipeline(m.bosque_elegido(), reg).fit(Xc, yc)
    return mod_pit, mod_comp


def predicciones_fuera_de_fold(d: dict) -> pd.DataFrame:
    """Para cada vuelta de 2023-2024, la predicción de modelos que no vieron esa carrera.

    Usa los mismos 4 pedazos por carrera de la v6. El puntaje de parada es el mismo que
    ``cross_val_predict`` de la sección 7 (con él se elige el umbral). El compuesto se
    predice para todas las vueltas del pedazo con el modelo de compuesto de ese fold
    (agregado para la app: en la v6 sólo se predecía el compuesto en paradas reales).
    """
    reg, tr, ct = d["registro"], d["train"], d["carreras_train"]
    Xp, yp, gp = m.split_datos(tr)
    fold_de = gp.map(m.folds_por_carrera(ct)).values
    puntaje = np.full(len(tr), np.nan)
    probas = np.full((len(tr), len(m.ORDEN)), np.nan)
    for k in range(m.N_FOLDS):
        entrena, valida = fold_de != k, fold_de == k
        est_pit = m.pipeline(m.bosque_elegido(), reg).fit(Xp[entrena], yp[entrena])
        puntaje[valida] = est_pit.predict_proba(Xp[valida])[:, 1]
        tr_k = tr[entrena]
        Xc, yc, _ = m.split_datos(tr_k.reset_index(drop=True), True)
        est_comp = m.pipeline(m.bosque_elegido(), reg).fit(Xc, yc)
        p = est_comp.predict_proba(Xp[valida])
        clases = list(est_comp.named_steps["modelo"].classes_)
        probas[valida] = p[:, [clases.index(c) for c in m.ORDEN]]
    salida = tr[m.CLAVE].copy()
    salida["puntaje"] = puntaje
    for i, c in enumerate(m.ORDEN):
        salida[f"p_{c}"] = probas[:, i]
    salida["fold"] = fold_de
    return salida


def elegir_umbral(y, puntaje) -> tuple[float, pd.DataFrame]:
    """Regla de la v6 (sección 7): máximo F1 de la clase 'para'; ante empate, el umbral más alto."""
    umbrales = np.round(np.arange(.10, .901, .025), 3)
    tabla = pd.DataFrame([{"umbral": float(u),
                           "f1": f1_score(y, puntaje >= u, zero_division=0),
                           "f2": fbeta_score(y, puntaje >= u, beta=2, zero_division=0),
                           "precision": precision_score(y, puntaje >= u, zero_division=0),
                           "recall": recall_score(y, puntaje >= u, zero_division=0),
                           "alarmas": int((puntaje >= u).sum())} for u in umbrales])
    mejor = tabla.f1.max()
    umbral = float(tabla.loc[np.isclose(tabla.f1, mejor), "umbral"].max())
    return umbral, tabla


def umbral_f2(tabla: pd.DataFrame, tope: float = 0.475) -> float:
    """Regla de la corrección (v7): máximo F2 fuera de pedazo entre umbrales <= 0,475; empate, el mayor."""
    t = tabla[tabla.umbral.le(tope + 1e-9)]
    return float(t.loc[np.isclose(t.f2, t.f2.max()), "umbral"].max())


# --------------------------------------------------------------------------
# Evaluación sobre 2025 (v6, sección 9)
# --------------------------------------------------------------------------
def _metricas_pit(y, p):
    return {"f1": f1_score(y, p, zero_division=0), "precision": precision_score(y, p, zero_division=0),
            "recall": recall_score(y, p, zero_division=0),
            "f1_macro": f1_score(y, p, average="macro", zero_division=0),
            "accuracy": accuracy_score(y, p), "alarmas": int(np.sum(p))}


def evaluar_test(d, mod_pit, mod_comp, umbral):
    tr, te = d["train"], d["test"]
    Xpt, ypt, _ = m.split_datos(te)
    Xc, yc, _ = m.split_datos(tr, True)
    Xct, yct, _ = m.split_datos(te, True)
    proba_pit = mod_pit.predict_proba(Xpt)[:, 1]
    pred_pit = (proba_pit >= umbral).astype(int)
    pred_comp = mod_comp.predict(Xct)
    from sklearn.dummy import DummyClassifier
    piso_comp = m.pipeline(DummyClassifier(strategy="most_frequent"), d["registro"]).fit(Xc, yc).predict(Xct)
    siempre = np.ones(len(ypt), dtype=int)
    rep = classification_report(yct, pred_comp, labels=m.ORDEN, zero_division=0, output_dict=True)
    res = {
        "pit": {"modelo": _metricas_pit(ypt, pred_pit), "nunca": _metricas_pit(ypt, np.zeros_like(siempre)),
                "siempre": _metricas_pit(ypt, siempre),
                "matriz": confusion_matrix(ypt, pred_pit).tolist()},
        "comp": {"modelo": {"f1_macro": f1_score(yct, pred_comp, average="macro", zero_division=0),
                            "accuracy": accuracy_score(yct, pred_comp),
                            "accuracy_balanceada": balanced_accuracy_score(yct, pred_comp)},
                 "piso": {"f1_macro": f1_score(yct, piso_comp, average="macro", zero_division=0),
                          "accuracy": accuracy_score(yct, piso_comp),
                          "accuracy_balanceada": balanced_accuracy_score(yct, piso_comp)},
                 "por_clase": {c: {k: rep[c][k] for k in ("precision", "recall", "f1-score", "support")}
                               for c in m.ORDEN},
                 "matriz": confusion_matrix(yct, pred_comp, labels=m.ORDEN).tolist()},
    }
    return res, proba_pit, pred_pit, pred_comp


# --------------------------------------------------------------------------
# Lectura de errores (v6, secciones 10 y 12)
# --------------------------------------------------------------------------
def lectura_errores(d, proba_pit, pred_pit, pred_comp, mod_comp) -> dict:
    te = d["test"]
    estado = mod_comp[:1].transform(te[m.COLS_X])  # variables históricas (mismo cálculo que el pipeline)
    lect = pd.concat([te.reset_index(drop=True),
                      estado.drop(columns=["lap_number", "circuit_short_name", "team_name"]).reset_index(drop=True)],
                     axis=1).assign(pred=pred_pit, proba=proba_pit)
    lect["sc"] = lect.safety_car_active.astype(str).str.lower().eq("true")
    lect["ultima_vuelta"] = lect.groupby("session_key").lap_number.transform("max")
    lect["tipo"] = np.select([lect.pit_stop & lect.pred.eq(1), ~lect.pit_stop & lect.pred.eq(1),
                              lect.pit_stop & lect.pred.eq(0)], ["VP", "FP", "FN"], "VN")
    paradas_reales = lect.loc[lect.pit_stop, ["session_key", "driver_number", "lap_number"]].rename(
        columns={"lap_number": "vuelta_parada"})
    orden = lect[["session_key", "driver_number", "lap_number"]].reset_index().sort_values("lap_number")
    pr = paradas_reales.sort_values("vuelta_parada")
    prox = pd.merge_asof(orden, pr, left_on="lap_number", right_on="vuelta_parada", by=["session_key", "driver_number"],
                         direction="forward", allow_exact_matches=False).set_index("index").sort_index()
    lect["faltan_para_parar"] = prox.vuelta_parada - lect.lap_number

    fp = lect[lect.tipo.eq("FP")]
    cat_fp = np.select([fp.faltan_para_parar.le(3), fp.faltan_para_parar.le(10)],
                       ["adelantada 1-3 vueltas", "adelantada 4-10 vueltas"], "sin parada en las 10 vueltas siguientes")
    tabla_fp = pd.Series(cat_fp).value_counts()
    fp_sin = fp[pd.Series(cat_fp, index=fp.index).eq("sin parada en las 10 vueltas siguientes")]

    al = lect[lect.pred.eq(1)].sort_values(m.CLAVE).copy()
    al["episodio"] = (al.groupby(["session_key", "driver_number"]).lap_number.diff().ne(1)).cumsum()
    ep = al.groupby("episodio").agg(vueltas=("lap_number", "size"), contiene_parada=("pit_stop", "any"),
                                    faltan=("faltan_para_parar", "last"))
    ep["termina_en_parada"] = ep.contiene_parada | ep.faltan.le(3)

    paradas = lect[lect.pit_stop].copy()
    alarma_previa = []
    for r in paradas.itertuples():
        mismo = lect[(lect.session_key == r.session_key) & (lect.driver_number == r.driver_number)]
        alarma_previa.append(bool(mismo.lap_number.between(r.lap_number - 3, r.lap_number - 1)
                                  .where(mismo.pred.eq(1), False).any()))
    paradas["alarma_previa_1a3"] = alarma_previa
    perfil = {}
    for t, g in paradas.groupby("tipo"):
        perfil[t] = {"paradas": int(len(g)), "edad_mediana": float(g.tyre_age_prev.median()),
                     "pct_safety_car": float(g.sc.mean()),
                     "pct_monta_lluvia": float(g.objetivo_compuesto.eq("LLUVIA").mean()),
                     "pct_neumatico_menor_8": float(g.tyre_age_prev.lt(8).mean()),
                     "pct_ultimas_10_vueltas": float((g.ultima_vuelta - g.lap_number).lt(10).mean()),
                     "pct_segunda_parada_o_mas": float(g.stops_before.ge(1).mean()),
                     "pct_con_alarma_1a3_antes": float(g.alarma_previa_1a3.mean())}

    # Tipo de parada (agregado para la app): reactiva (safety car o neumático de lluvia) o planificada.
    paradas["contexto"] = np.select([paradas.sc, paradas.objetivo_compuesto.eq("LLUVIA")],
                                    ["Con safety car", "A neumático de lluvia"], "En seco, sin safety car")
    por_contexto = []
    for ctx in ["En seco, sin safety car", "Con safety car", "A neumático de lluvia"]:
        g = paradas[paradas.contexto.eq(ctx)]
        por_contexto.append({"contexto": ctx, "paradas": int(len(g)), "anticipadas": int(g.pred.eq(1).sum()),
                             "pct": float(g.pred.eq(1).mean())})

    # Compuesto (v6, celda 53)
    comp = te[te.pit_stop].reset_index(drop=True).assign(predicho=pred_comp)
    comp = comp.merge(lect.loc[lect.pit_stop, m.CLAVE + ["compound_prev", "used_medium", "field_lluvia_prev"]],
                      on=m.CLAVE, how="left")
    comp["acierto"] = comp.objetivo_compuesto.eq(comp.predicho)
    por_carrera = comp.groupby("meeting_name").acierto.agg(["size", "mean"]).sort_values("mean")
    errores = (comp.loc[~comp.acierto].groupby(["objetivo_compuesto", "predicho"]).size()
               .sort_values(ascending=False).head(6))
    belgica = comp[comp.meeting_name.str.contains("Belgian")]

    # Sistema integrado (v6, celdas 59-60)
    prob_total = mod_comp.predict_proba(te[m.COLS_X])
    clases = mod_comp.named_steps["modelo"].classes_
    recomendado = clases[np.argmax(prob_total, axis=1)]
    salida = te[m.CLAVE + ["pit_stop", "objetivo_compuesto"]].copy()
    salida["recomendar"] = pred_pit.astype(bool)
    salida["comp_rec"] = np.where(salida.recomendar, recomendado, "NO_APLICA")
    detectadas = salida.pit_stop & salida.recomendar
    ambas = detectadas & salida.objetivo_compuesto.eq(salida.comp_rec)
    hard_ok = int((detectadas & salida.objetivo_compuesto.eq("HARD")).sum())

    # Ejemplo de racha larga de falsas alarmas (v6, celda 51)
    ej = ep[~ep.termina_en_parada].sort_values("vueltas", ascending=False).index[0]
    ejemplo = al[al.episodio.eq(ej)].iloc[0]

    return {
        "fp_total": int(len(fp)),
        "fp_categorias": {k: int(v) for k, v in tabla_fp.items()},
        "fp_sin_cercana_no_vuelve_a_parar": float(fp_sin.faltan_para_parar.isna().mean()),
        "episodios": int(len(ep)), "episodio_mediana_vueltas": float(ep.vueltas.median()),
        "episodios_terminan_en_parada": float(ep.termina_en_parada.mean()),
        "perfil": perfil,
        "alarma_exacta": float(paradas.pred.eq(1).mean()),
        "alarma_ventana_3": float((paradas.pred.eq(1) | paradas.alarma_previa_1a3).mean()),
        "por_contexto": por_contexto,
        "comp_por_compuesto_entrada": {k: {"paradas": int(g.size), "acierto": float(g.mean())}
                                       for k, g in comp.groupby("compound_prev").acierto},
        "comp_peores_carreras": [{"carrera": k, "paradas": int(r["size"]), "acierto": float(r["mean"])}
                                 for k, r in por_carrera.head(6).iterrows()],
        "comp_errores": [{"real": a, "predicho": b, "paradas": int(v)} for (a, b), v in errores.items()],
        "belgica": {"paradas": int(len(belgica)), "aciertos": int(belgica.acierto.sum())},
        "sistema": {"vueltas": int(len(salida)), "paradas": int(salida.pit_stop.sum()),
                    "alarmas": int(salida.recomendar.sum()), "detectadas": int(detectadas.sum()),
                    "ambas": int(ambas.sum()), "hard_ok": hard_ok},
        "ejemplo_racha": {"carrera": ejemplo.meeting_name, "piloto": ejemplo.full_name,
                          "vuelta": int(ejemplo.lap_number), "faltan": float(ejemplo.faltan_para_parar)},
        "_paradas": paradas, "_lect": lect,
    }


# --------------------------------------------------------------------------
# Datos descriptivos (v6, secciones 1.1, 1.2 y 2.1)
# --------------------------------------------------------------------------
def hipotesis_4(raw_pits: pd.DataFrame) -> dict:
    h4 = raw_pits[m.CLAVE + ["safety_car_active", "new_compound"]].copy()
    h4["safety_car"] = h4["safety_car_active"].astype("string").str.lower().eq("true")
    h4["lluvia"] = h4["new_compound"].isin(["INTERMEDIATE", "WET"])
    tot = {}
    for sc, g in h4.groupby("safety_car"):
        tot["con" if sc else "sin"] = {"paradas": int(len(g)), "pct_lluvia": float(g.lluvia.mean()),
                                       "carreras": int(g.session_key.nunique())}
    seco = h4[~h4.lluvia]
    tabla = pd.crosstab(seco.safety_car, seco.new_compound, normalize="index").reindex(columns=["SOFT", "MEDIUM", "HARD"])
    n = seco.safety_car.value_counts()
    filas = []
    for sc in [False, True]:
        for c in ["SOFT", "MEDIUM", "HARD"]:
            filas.append({"situacion": "Con safety car" if sc else "Sin safety car", "compuesto": c,
                          "pct": float(tabla.loc[sc, c]), "paradas": int(n[sc])})
    brecha = float(tabla.loc[False, "HARD"] - tabla.loc[True, "HARD"])
    return {"totales": tot, "seco": filas, "brecha_hard_seco": brecha,
            "paradas_lluvia": int(h4.lluvia.sum()), "lluvia_con_sc": int((h4.lluvia & h4.safety_car).sum()),
            "carreras_lluvia": int(h4.loc[h4.lluvia, "session_key"].nunique())}


def separacion(x: pd.Series, y: pd.Series) -> float:
    """Separación estandarizada de la Entrega 2 (celda 53)."""
    x, y = x.dropna(), y.dropna()
    return float(abs(x.mean() - y.mean()) / np.sqrt((x.std() ** 2 + y.std() ** 2) / 2))


def hipotesis_2_y_4_originales(raw: pd.DataFrame, raw_pits: pd.DataFrame) -> dict:
    """Números originales de la Entrega 2: H2 (posición) y H4 sobre todas las paradas."""
    h2 = raw[raw["pit_data_available"] == True]  # noqa: E712
    para = h2["pit_stop"].astype(str).str.lower().eq("true")
    pos_pit, pos_no = h2.loc[para, "position"], h2.loc[~para, "position"]
    sc = raw_pits["safety_car_active"].astype(str).str.lower().eq("true")
    hard = raw_pits["new_compound"].eq("HARD")
    return {"h2_sep": separacion(pos_pit, pos_no), "h2_media_para": float(pos_pit.mean()),
            "h2_media_sigue": float(pos_no.mean()),
            "h4_brecha_todas": float(hard[~sc].mean() - hard[sc].mean()),
            "h4_hard_sin_todas": float(hard[~sc].mean()), "h4_hard_con_todas": float(hard[sc].mean())}


def hipotesis_1(d: dict, mod_comp) -> dict:
    pob = d["poblacion"]
    estado = mod_comp[:1].transform(pob[m.COLS_X])
    datos = pd.DataFrame({"pit_stop": pob.pit_stop.values, "tyre_age_prev": estado.tyre_age_prev.values})
    bins = np.arange(0, 61, 2)
    filas = []
    for valor, etiqueta in [(False, "Sigue en pista"), (True, "Entra a boxes")]:
        e = datos.loc[datos.pit_stop.eq(valor), "tyre_age_prev"].dropna()
        cuenta, _ = np.histogram(e, bins=bins)
        for b, c in zip(bins[:-1], cuenta):
            filas.append({"grupo": etiqueta, "desde": int(b), "hasta": int(b + 2), "pct": float(100 * c / len(e)),
                          "n_grupo": int(len(e))})
    desc = datos.groupby("pit_stop").tyre_age_prev.describe()
    return {"histograma": filas,
            "resumen": {("para" if k else "sigue"): {"n": int(r["count"]), "q1": float(r["25%"]),
                                                    "mediana": float(r["50%"]), "q3": float(r["75%"])}
                        for k, r in desc.iterrows()},
            "_estado": estado}


# --------------------------------------------------------------------------
# Correcciones de la Entrega 3 (CorreccionesEntrega3.md · notebook v7), en el entorno de la v6
# --------------------------------------------------------------------------
ORDEN_DISTANCIA = ["1 vuelta", "2–3 vueltas", "4–10 vueltas", "más de 10 vueltas", "sin parada posterior"]


def correcciones_e3(L: dict, proba_test, y_test, mod_pit, mod_comp) -> dict:
    """Lo que pidió la devolución de la Entrega 3, con las definiciones de la v7.

    * umbrales alternativos sobre 2025 (descriptivo: el umbral se eligió antes, con 2023-2024);
    * falsas alarmas por distancia a la próxima parada real del mismo piloto;
    * cobertura con tolerancia: paradas con alarma en esa vuelta o en las k anteriores;
    * importancia del bosque sin permutación (disminución media de impureza, MDI).
    """
    from sklearn.metrics import confusion_matrix

    lect = L["_lect"]
    filas_u = []
    for u in [0.30, 0.40, 0.45, 0.475, 0.50]:
        pred = (proba_test >= u).astype(int)
        vn, fp, fn, vp = confusion_matrix(y_test, pred, labels=[0, 1]).ravel()
        filas_u.append({"umbral": u, "vp": int(vp), "fp": int(fp), "fn": int(fn),
                        "recall": vp / (vp + fn), "precision": vp / (vp + fp)})

    fp = lect[lect.tipo.eq("FP")]
    dist = fp.faltan_para_parar
    cat = np.select([dist.eq(1), dist.between(2, 3), dist.between(4, 10), dist.gt(10)], ORDEN_DISTANCIA[:4],
                    ORDEN_DISTANCIA[4])
    conteo = pd.Series(cat).value_counts().reindex(ORDEN_DISTANCIA, fill_value=0)
    distancias = [{"categoria": k, "fp": int(v), "pct": float(v / len(fp))} for k, v in conteo.items()]

    alarmas = set(map(tuple, lect.loc[lect.pred.eq(1), ["session_key", "driver_number", "lap_number"]].values))
    paradas = lect.loc[lect.pit_stop, ["session_key", "driver_number", "lap_number"]].values
    cobertura = []
    for k in range(4):
        ok = sum(any((s, dn, lap - j) in alarmas for j in range(k + 1)) for s, dn, lap in paradas)
        cobertura.append({"k": k, "paradas": int(ok), "pct": float(ok / len(paradas))})

    def mdi(mod):
        nombres = mod.named_steps["preparar"].get_feature_names_out()
        imp = pd.Series(mod.named_steps["modelo"].feature_importances_, index=nombres)
        origen = [n.split("__", 1)[1] for n in nombres]
        origen = [next(c for c in m.CAT if o.startswith(c + "_")) if o not in m.NUM else o for o in origen]
        return (imp.groupby(origen).sum().sort_values(ascending=False)
                .rename_axis("variable").reset_index(name="importancia").to_dict("records"))

    return {"umbrales_2025": filas_u, "distancias": distancias, "fp_total": int(len(fp)),
            "fp_mediana": float(dist.median()), "cobertura": cobertura,
            "mdi": {"pit": mdi(mod_pit), "comp": mdi(mod_comp)}}
