"""Pruebas de la aplicación de la Entrega 4.

Comprueban que lo publicado en ``Entrega4/sitio`` sale del modelo real:
* los puntajes guardados para «Explorá» son los de ``predict_proba`` del ``.joblib``;
* ``modelo.js`` (lo que usa «Probá el modelo») da lo mismo que scikit-learn;
* ``HistoriaCausal`` no mira el futuro;
* la última construcción coincide con los números del notebook v6.

Necesitan haber corrido ``python build_app.py``; si faltan los artefactos, se omiten.
"""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
SITIO = RAIZ / "Entrega4" / "sitio"
ART = RAIZ / "Entrega4" / "artefactos"
CARRERA_2025 = 9693  # Australia 2025 (test): la predicción guardada es la del modelo final

pytestmark = pytest.mark.skipif(not (ART / "construccion.json").exists(), reason="falta correr build_app.py")


def filas_carrera(sk):
    d = json.loads((SITIO / "datos" / "carreras" / f"{sk}.json").read_text(encoding="utf-8"))
    t = pd.DataFrame(d["filas"], columns=d["columnas"])
    info = {a: v for a, v in d["pilotos"].items()}
    t["team_name"] = t.piloto.map(lambda a: info[a][1])
    t["circuit_short_name"] = d["circuito"]
    t["lap_number"] = t.vuelta
    total = t[["n_soft", "n_medium", "n_hard", "n_lluvia"]].sum(axis=1).replace(0, np.nan)
    for c in ["soft", "medium", "hard", "lluvia"]:
        t[f"field_{c}_prev"] = t[f"n_{c}"] / total
    return t


def test_construccion_coincide_con_v6():
    c = json.loads((ART / "construccion.json").read_text(encoding="utf-8"))
    distintos = [f for f in c["comparacion_v6"] if not f["coincide"]]
    assert not distintos, distintos
    assert c["umbral"] == 0.475


def test_puntajes_de_explora_son_los_del_modelo_guardado():
    import joblib
    from src import modelo as M
    mod = joblib.load(ART / "f1_modelo_pit_stop.joblib")
    t = filas_carrera(CARRERA_2025)
    esperado = mod[1:].predict_proba(t[M.FEATURES])[:, 1]
    assert np.allclose(esperado, t.puntaje, atol=1e-6)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está instalado")
def test_modelo_js_igual_a_scikit_learn(tmp_path):
    import joblib
    from src import modelo as M
    t = filas_carrera(CARRERA_2025)
    filas = [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in t[M.FEATURES].to_dict("records")]
    (tmp_path / "filas.json").write_text(json.dumps(filas), encoding="utf-8")
    for nombre, archivo in [("parada", "f1_modelo_pit_stop.joblib"), ("compuesto", "f1_modelo_new_compound.joblib")]:
        script = tmp_path / "correr.mjs"
        script.write_text(
            "import {readFileSync} from 'node:fs';\n"
            f"import {{predecir}} from '{(RAIZ / 'Entrega4' / 'app' / 'modelo.js').as_uri()}';\n"
            f"const m = JSON.parse(readFileSync('{(SITIO / 'datos' / f'modelo_{nombre}.json').as_posix()}', 'utf8'));\n"
            f"const f = JSON.parse(readFileSync('{(tmp_path / 'filas.json').as_posix()}', 'utf8'));\n"
            "console.log(JSON.stringify(f.map(x => predecir(m, x))));\n", encoding="utf-8")
        salida = subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout
        js = np.array(json.loads(salida))
        py = joblib.load(ART / archivo)[1:].predict_proba(t[M.FEATURES])
        py = py[:, 1] if js.ndim == 1 else py
        assert np.abs(js - py).max() < 1e-9


def test_historia_causal_no_mira_el_futuro():
    from src import modelo as M
    d = M.preparar_todo()
    v = d["vueltas"]
    pob = d["poblacion"]
    muestra = pob[pob.session_key.eq(CARRERA_2025)].sample(30, random_state=M.SEED)
    completo = M.HistoriaCausal(M.RegistroCarreras(v)).transform(muestra[M.COLS_X])
    for i, fila in muestra.iterrows():
        sin_futuro = v[~(v.session_key.eq(fila.session_key) & v.lap_number.ge(fila.lap_number))]
        rec = M.HistoriaCausal(M.RegistroCarreras(sin_futuro)).transform(muestra.loc[[i], M.COLS_X])
        assert rec.astype(str).equals(completo.loc[[i]].astype(str))
