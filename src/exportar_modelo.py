"""Exporta los pipelines entrenados (sin el paso HistoriaCausal) a JSON para el navegador.

El JSON contiene exactamente los parámetros aprendidos: medianas del imputador,
media y escala del ``StandardScaler``, categorías del ``OneHotEncoder`` y cada nodo
de cada árbol del random forest (variable, umbral, hijos y probabilidades de las
hojas). ``Entrega4/app/modelo.js`` los recorre igual que scikit-learn, y
``verificar_paridad`` comprueba con Node.js que da lo mismo que ``predict_proba``.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from src import modelo as m


def _valor_json(v):
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def exportar(pipeline_entrenado, binario: bool) -> dict:
    prep = pipeline_entrenado.named_steps["preparar"]
    rf = pipeline_entrenado.named_steps["modelo"]
    num_pipe = prep.named_transformers_["num"]
    cat_pipe = prep.named_transformers_["cat"]
    nums = list(prep.transformers_[0][2])
    cats = list(prep.transformers_[1][2])
    assert nums == m.NUM and cats == m.CAT
    arboles = []
    clases = [str(c) for c in rf.classes_]
    for est in rf.estimators_:
        t = est.tree_
        hoja = t.children_left == -1
        valores = t.value[:, 0, :]
        valores = valores / valores.sum(axis=1, keepdims=True)
        if binario:
            v = np.where(hoja, valores[:, 1], 0.0)
            v_lista = [float(x) for x in v]
        else:
            v_lista = [[float(x) for x in fila] if h else 0 for fila, h in zip(valores, hoja)]
        arboles.append({"f": [int(x) for x in t.feature], "t": [float(x) for x in t.threshold],
                        "l": [int(x) for x in t.children_left], "r": [int(x) for x in t.children_right],
                        "v": v_lista})
    return {
        "numericas": nums, "categoricas": cats, "clases": clases, "binario": binario,
        "medianas": [float(x) for x in num_pipe.named_steps["imputar"].statistics_],
        "media": [float(x) for x in num_pipe.named_steps["escalar"].mean_],
        "escala": [float(x) for x in num_pipe.named_steps["escalar"].scale_],
        "moda_cat": [_valor_json(x) for x in cat_pipe.named_steps["imputar"].statistics_],
        "categorias": [[_valor_json(c) for c in cs] for cs in cat_pipe.named_steps["onehot"].categories_],
        "n_entrada": int(len(prep.get_feature_names_out())),
        "arboles": arboles,
    }


def filas_json(estado: pd.DataFrame) -> list[dict]:
    return [{k: _valor_json(v) for k, v in fila.items()} for fila in estado[m.FEATURES].to_dict("records")]


def verificar_paridad(modelo_json: dict, pipeline_entrenado, estado: pd.DataFrame, modelo_js: Path) -> dict:
    """Corre modelo.js en Node.js sobre todas las filas y lo compara con predict_proba."""
    node = shutil.which("node")
    if node is None:
        return {"verificado": False, "motivo": "Node.js no está instalado"}
    esperado = pipeline_entrenado[1:].predict_proba(estado[m.FEATURES])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "modelo.json").write_text(json.dumps(modelo_json), encoding="utf-8")
        (tmp / "filas.json").write_text(json.dumps(filas_json(estado)), encoding="utf-8")
        script = tmp / "correr.mjs"
        script.write_text(
            "import {readFileSync, writeFileSync} from 'node:fs';\n"
            f"import {{predecir}} from '{modelo_js.resolve().as_uri()}';\n"
            "const mod = JSON.parse(readFileSync(process.argv[2], 'utf8'));\n"
            "const filas = JSON.parse(readFileSync(process.argv[3], 'utf8'));\n"
            "writeFileSync(process.argv[4], JSON.stringify(filas.map(f => predecir(mod, f))));\n",
            encoding="utf-8")
        subprocess.run([node, str(script), str(tmp / "modelo.json"), str(tmp / "filas.json"), str(tmp / "salida.json")],
                       check=True, capture_output=True, text=True)
        obtenido = np.array(json.loads((tmp / "salida.json").read_text(encoding="utf-8")))
    if obtenido.ndim == 1:
        obtenido = np.column_stack([1 - obtenido, obtenido])
    dif = float(np.abs(obtenido - esperado).max())
    clase_igual = float((obtenido.argmax(1) == esperado.argmax(1)).mean())
    return {"verificado": dif < 1e-9, "filas": int(len(estado)), "max_diferencia": dif,
            "misma_clase": clase_igual}
