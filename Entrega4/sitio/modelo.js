// Inferencia del modelo de la Entrega 3 en el navegador.
//
// Recorre los parámetros exportados por src/exportar_modelo.py exactamente como
// scikit-learn 1.6.1:
//   1. SimpleImputer(median) y StandardScaler en las variables numéricas,
//   2. SimpleImputer(most_frequent) y OneHotEncoder(handle_unknown="ignore") en las categóricas,
//   3. RandomForestClassifier.predict_proba: promedio de las hojas de cada árbol.
// scikit-learn convierte la entrada a float32 antes de recorrer los árboles
// (sklearn.tree._tree.DTYPE); Math.fround reproduce esa conversión.
// build_app.py comprueba con Node.js que el resultado coincide con predict_proba
// en todas las vueltas del dataset.

function faltante(v) {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

export function vectorEntrada(mod, fila) {
  const x = [];
  mod.numericas.forEach((nombre, i) => {
    const v = faltante(fila[nombre]) ? mod.medianas[i] : Number(fila[nombre]);
    x.push((v - mod.media[i]) / mod.escala[i]);
  });
  mod.categoricas.forEach((nombre, j) => {
    const v = faltante(fila[nombre]) ? mod.moda_cat[j] : fila[nombre];
    for (const c of mod.categorias[j]) x.push(v === c ? 1 : 0);
  });
  if (x.length !== mod.n_entrada) throw new Error(`Vector de ${x.length} columnas; el modelo espera ${mod.n_entrada}.`);
  return x.map(Math.fround);
}

function hoja(arbol, x) {
  let n = 0;
  while (arbol.l[n] !== -1) {
    n = x[arbol.f[n]] <= arbol.t[n] ? arbol.l[n] : arbol.r[n];
  }
  return arbol.v[n];
}

// Binario: devuelve la probabilidad de la clase 1 (parada).
// Multiclase: devuelve un arreglo en el orden de mod.clases.
export function predecir(mod, fila) {
  const x = vectorEntrada(mod, fila);
  const k = mod.arboles.length;
  if (mod.binario) {
    let s = 0;
    for (const a of mod.arboles) s += hoja(a, x);
    return s / k;
  }
  const s = new Array(mod.clases.length).fill(0);
  for (const a of mod.arboles) {
    const v = hoja(a, x);
    for (let c = 0; c < s.length; c++) s[c] += v[c];
  }
  return s.map((v) => v / k);
}
