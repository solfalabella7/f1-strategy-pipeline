"""Construye el notebook autocontenido de correcciones a partir de la preparación v6."""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
base = json.loads((HERE / 'Entrega3_F1_v6.ipynb').read_text(encoding='utf-8'))
cells = []


def agregar(texto, tipo='code'):
    c = {'cell_type': tipo, 'metadata': {}, 'source': texto.splitlines(keepends=True)}
    if tipo == 'code':
        c.update(execution_count=None, outputs=[])
    cells.append(c)


agregar('''# Entrega 3 · Correcciones de evaluación (v7)

Complemento autocontenido de `Entrega3_F1_v6.ipynb`. Conserva su preparación,
variables, particiones por carrera y los dos random forest seleccionados. No repite
la búsqueda de familias ni cambia los hiperparámetros: se concentra en la devolución
de `CorreccionesEntrega3.md`. No modifica archivos de la Entrega 4.

**Protocolo fijado antes de ejecutar:** comparar 0,475 (referencia v6), 0,50 y umbrales
inferiores. Elegir el máximo F2 sobre predicciones fuera de fold de 2023–2024 entre
umbrales <= 0,475; desempatar por el mayor umbral. F2 pondera más el recall, pero
se publica su costo en precisión y volumen de alarmas. No se promete una mejora
operativa por cambiar el criterio. 2025 ya fue examinado y es evaluación descriptiva,
no un test virgen. Los puntajes del bosque balanceado no son probabilidades calibradas.

Los folds se reutilizan del trabajo previo: los resultados OOF sirven para elegir
el umbral, no constituyen una estimación independiente del proceso completo de selección.
Las ventanas temporales son retrospectivas y nunca entran como features.

Ejecutar todo desde `Entrega3` con los CSV Silver locales disponibles. Las tablas
y figuras se guardan en `resultados_correcciones/`. Las versiones instaladas se imprimen:
pueden producir diferencias respecto de scikit-learn 1.6.1 usado en la v6.
''', 'markdown')
for i in [2, 3, 4, 6, 15, 17, 23, 27]:
    c = copy.deepcopy(base['cells'][i])
    c['execution_count'], c['outputs'] = None, []
    cells.append(c)
agregar((HERE / 'analisis_correcciones.py').read_text(encoding='utf-8'))
agregar('''## 1 · Referencia y selección del umbral
Ambos bosques conservan 150 árboles, profundidad 12, hoja mínima 10 y
`balanced_subsample`. Se conserva la referencia 0,475 aunque otra versión de las
librerías produzca un máximo F1 diferente. La regla F2 se aplica solo al detector.
''', 'markdown')
agregar('''from sklearn.metrics import precision_recall_curve, average_precision_score
OUT = Path.cwd() / 'resultados_correcciones'
OUT.mkdir(exist_ok=True)
def guardar_figura(nombre):
    plt.gcf().savefig(OUT / (nombre + '.png'), dpi=150, bbox_inches='tight')
    plt.show()

def bosque_v6():
    return pipeline(RandomForestClassifier(n_estimators=150, max_depth=12,
                    min_samples_leaf=10, class_weight='balanced_subsample', random_state=SEED, n_jobs=-1))
modelo_pit, modelo_comp = bosque_v6(), bosque_v6()
probas_pit_oof = cross_val_predict(modelo_pit, Xpit, ypit, cv=cvpit,
                                  method='predict_proba', n_jobs=1)[:, 1]
UMBRAL_BASE = 0.475
grilla = sorted(set(np.round(np.arange(.025, .501, .025), 3)) | {UMBRAL_BASE})
tabla_umbrales = pd.DataFrame([metricas_umbral(ypit, probas_pit_oof, u) for u in grilla])
elegibles = tabla_umbrales[tabla_umbrales.umbral.le(UMBRAL_BASE)]
UMBRAL_NUEVO = float(elegibles.sort_values(['F2', 'umbral'], ascending=False).iloc[0].umbral)
tabla_umbrales.to_csv(OUT / 'umbrales_oof.csv', index=False)
display(tabla_umbrales.round(4))
print('Umbral F2 elegido exclusivamente en OOF:', UMBRAL_NUEVO)
precision, recall, _ = precision_recall_curve(ypit, probas_pit_oof)
fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(recall, precision, label='Curva OOF')
comparar = sorted({0.50, UMBRAL_BASE, UMBRAL_NUEVO, 0.10, 0.20, 0.30, 0.40})
for u in comparar:
    m = metricas_umbral(ypit, probas_pit_oof, u)
    ax.scatter(m['recall'], m['precision'])
    ax.annotate(f'{u:.3f}', (m['recall'], m['precision']), xytext=(-4 if m['recall'] > .95 else 4, 5),
                ha='right' if m['recall'] > .95 else 'left', textcoords='offset points')
ax.axhline(ypit.mean(), color='gray', linestyle='--', label='Prevalencia de paradas')
ax.set(xlabel='Recall', ylabel='Precisión', title='Precisión–recall: etiquetas = umbral', xlim=(0, 1), ylim=(0, 1))
ax.legend(); guardar_figura('precision_recall_oof')
print('Average precision OOF:', average_precision_score(ypit, probas_pit_oof))
modelo_pit.fit(Xpit, ypit)
modelo_comp.fit(Xcomp, ycomp)
proba_test = modelo_pit.predict_proba(Xpit_test)[:, 1]
''')
agregar('''## 2 · Matrices, todas las paradas y todas las falsas alarmas
Se exportan todas las filas, no solo ejemplos. Los conteos usan la población evaluable
de la v6 (vueltas con historia previa), no todas las paradas del CSV bruto.
La normalización por fila mide recuperación de clases; por columna, confiabilidad
de las predicciones. El umbral queda congelado antes de mirar estas tablas de 2025.
''', 'markdown')
agregar('''umbrales_comparacion = sorted({0.30, 0.40, 0.45, 0.50, UMBRAL_BASE, UMBRAL_NUEVO})
auditorias, temporales, conteos_fp = {}, [], []
for nombre, datos, p in [('oof', descr[descr.season.lt(2025)].reset_index(drop=True), probas_pit_oof),
                          ('2025', descr[descr.season.eq(2025)].reset_index(drop=True), proba_test)]:
    resumen = []
    for u in umbrales_comparacion:
        t, ep, reales = auditar_alarmas(datos, p, u)
        auditorias[nombre, u] = (t, ep, reales)
        resumen.append(metricas_umbral(t.real, p, u))
        prefijo = f'{nombre}_u{u:.3f}'
        for sufijo, df in [('vueltas', t), ('falsos_positivos', t[t.tipo.eq('FP')]),
                            ('paradas_reales', reales), ('episodios', ep)]:
            df.to_csv(OUT / f'{prefijo}_{sufijo}.csv', index=False)
        temporales.append(resumen_temporal(t, ep, reales).assign(conjunto=nombre, umbral=u))
        conteos_fp.append(t[t.tipo.eq('FP')].categoria_fp.value_counts().rename('FP').reset_index()
                          .assign(conjunto=nombre, umbral=u))
        fig, axs = plt.subplots(1, 3, figsize=(13, 4))
        for ax, norm, titulo in zip(axs, [None, 'true', 'pred'], ['Conteos', 'Por clase real', 'Por predicción']):
            ConfusionMatrixDisplay.from_predictions(t.real, t.alarma, labels=[False, True],
                display_labels=['no para', 'para'], normalize=norm,
                values_format='d' if norm is None else '.2f', ax=ax, colorbar=False)
            ax.set_title(titulo)
        fig.suptitle(f'{nombre}: umbral {u:.3f}')
        fig.tight_layout(); guardar_figura(prefijo + '_matrices')
    display(pd.DataFrame(resumen).round(4))
    pd.DataFrame(resumen).to_csv(OUT / f'{nombre}_comparacion.csv', index=False)
temporal = pd.concat(temporales, ignore_index=True)
fp_categorias = pd.concat(conteos_fp, ignore_index=True)
temporal.to_csv(OUT / 'metricas_temporales.csv', index=False)
fp_categorias.to_csv(OUT / 'categorias_fp.csv', index=False)
display(temporal.round(4))
''')
agregar('''## 3 · Distancia y episodios: métricas complementarias
Un FP exacto sigue siendo FP aunque haya una parada después. La fracción de alarmas
cercanas NO es la precisión exacta. Cobertura cuenta cada parada una sola vez.
Para precisión/recall por episodios se empareja cada episodio con una sola parada y
cada parada con un solo episodio. Una parada interrumpe la racha. Se permite coincidencia
en la vuelta real o en las k anteriores, nunca una alarma posterior.

La distancia usa la próxima parada, no la parada más cercana en ambas direcciones.
Sin parada posterior observada se reporta por separado: puede ser el stint final,
un retiro o un final de observación. No se imputa una distancia ni una intención del piloto.
''', 'markdown')
agregar('''orden_fp = ['1 vuelta', '2–3 vueltas', '4–10 vueltas', '>10 vueltas', 'sin parada posterior observada']
for nombre in ['oof', '2025']:
    cats = fp_categorias[fp_categorias.conjunto.eq(nombre)].pivot(index='umbral', columns='categoria_fp', values='FP').reindex(columns=orden_fp).fillna(0)
    display(cats)
    display(cats.div(cats.sum(axis=1).replace(0, np.nan), axis=0).round(3))
    cats.plot.bar(stacked=True, figsize=(10, 5))
    plt.ylabel('Vueltas con falsa alarma'); plt.title(f'{nombre}: distancia a la próxima parada')
    plt.legend(bbox_to_anchor=(1.02, 1)); guardar_figura(nombre + '_distancias_fp')
    fig, ax = plt.subplots(figsize=(8, 4))
    for u in umbrales_comparacion:
        r = temporal[temporal.conjunto.eq(nombre) & temporal.umbral.eq(u)]
        ax.plot(r.tolerancia, r.cobertura_paradas, marker='o', label=f'umbral {u:.3f}')
    ax.set(xlabel='Tolerancia de anticipación (vueltas)', ylabel='Fracción de paradas con aviso', xticks=range(4), ylim=(0, 1))
    ax.legend(); guardar_figura(nombre + '_cobertura')
    filas = []
    for u in umbrales_comparacion:
        t, ep, reales = auditorias[nombre, u]
        fp = t[t.tipo.eq('FP')]
        d = fp.distancia_proxima_parada.dropna()
        filas.append({'umbral': u, 'FP': len(fp), 'FP_con_parada_posterior': len(d),
                      'distancia_mediana': d.median(), 'distancia_p90': d.quantile(.9),
                      'FP_sin_parada_posterior': fp.distancia_proxima_parada.isna().sum(),
                      'FP_sin_parada_y_menos_3_vueltas_observadas': (fp.distancia_proxima_parada.isna() & fp.vueltas_observadas_restantes.lt(3)).sum(),
                      'episodios': len(ep), 'duracion_mediana': ep.duracion.median(), 'duracion_p90': ep.duracion.quantile(.9)})
    display(pd.DataFrame(filas).round(3))
    pd.DataFrame(filas).to_csv(OUT / f'{nombre}_distancias_episodios.csv', index=False)
''')
agregar('''## 4 · Casos verificables y límites de interpretación
Se selecciona determinísticamente un caso por categoría (máximo puntaje, desempate
por carrera/piloto/vuelta). Son ejemplos descriptivos, no prueba de estrategia óptima.
En cada caso se muestra la trayectoria completa para no ocultar alarmas persistentes.
Safety car se conserva solo para descripción, tal como en la v6.
''', 'markdown')
agregar('''t, ep, reales = auditorias['2025', UMBRAL_NUEVO]
casos = []
for etiqueta, mascara in [('FP cercano', t.tipo.eq('FP') & t.distancia_proxima_parada.between(1, 3)),
                          ('FP lejano', t.tipo.eq('FP') & t.distancia_proxima_parada.gt(10)),
                          ('FP sin parada posterior', t.tipo.eq('FP') & t.distancia_proxima_parada.isna()),
                          ('Parada omitida', t.tipo.eq('FN'))]:
    candidatos = t[mascara].sort_values(['puntaje'] + CLAVE, ascending=[False, True, True, True])
    if candidatos.empty:
        print(etiqueta, ': no hay casos'); continue
    r = candidatos.iloc[0]
    casos.append(r.to_dict() | {'caso': etiqueta})
    g = t[t.session_key.eq(r.session_key) & t.driver_number.eq(r.driver_number)].sort_values('lap_number')
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(g.lap_number, g.puntaje, label='Puntaje')
    ax.axhline(UMBRAL_NUEVO, color='orange', linestyle='--', label='Umbral nuevo')
    ax.axhline(UMBRAL_BASE, color='gray', linestyle=':', label='Umbral v6')
    for j, lap in enumerate(g.loc[g.real, 'lap_number']):
        ax.axvline(lap, color='green', alpha=.6, label='Parada real' if j == 0 else None)
    ax.scatter([r.lap_number], [r.puntaje], color='red', label='Caso seleccionado')
    ax.set(xlabel='Vuelta', ylabel='Puntaje', title=f'{etiqueta}: {r.meeting_name} · {r.full_name}', ylim=(0, 1))
    ax.legend(); guardar_figura('caso_' + str(len(casos)))
casos = pd.DataFrame(casos)
casos.to_csv(OUT / 'casos.csv', index=False)
display(casos[['caso', 'meeting_name', 'full_name', 'lap_number', 'puntaje', 'distancia_proxima_parada', 'tyre_age_prev', 'compound_prev', 'safety_car_active']])
perfil = t[t.real].groupby('tipo').agg(paradas=('real', 'size'),
    edad_mediana=('tyre_age_prev', 'median'),
    fraccion_lluvia=('objetivo_compuesto', lambda x: x.eq('LLUVIA').mean()),
    fraccion_safety_car=('safety_car_active', lambda x: x.astype(str).str.lower().eq('true').mean()))
display(perfil); perfil.to_csv(OUT / 'perfil_paradas_detectadas_omitidas.csv')
''')
agregar('''## 5 · Qué variables aportan a cada random forest
Permutación sobre variables construidas en el fold de validación. Para parada se mide
F1 y F2 con el umbral nuevo, además de F1 con el umbral v6; para compuesto, F1 macro.
La caída puede ser negativa por ruido o redundancia: no prueba que una variable sea
inútil ni que el modelo no la use. Se informan todos los atributos y su variabilidad.
Los atributos excluidos tampoco son atributos que el bosque haya aprendido a ignorar.
''', 'markdown')
agregar('''def score_umbral(umbral, beta):
    def puntuar(est, X, y):
        pred = est.predict_proba(X)[:, list(est.classes_).index(1)] >= umbral
        return fbeta_score(y, pred, beta=beta, zero_division=0)
    return puntuar

importancias = []
for nombre, modelo, X, y, cv in [('parada', modelo_pit, Xpit, ypit, cvpit),
                                  ('compuesto', modelo_comp, Xcomp, ycomp, cvcomp)]:
    scores = {'F1_umbral_v6': score_umbral(UMBRAL_BASE, 1),
              'F1_umbral_nuevo': score_umbral(UMBRAL_NUEVO, 1),
              'F2_umbral_nuevo': score_umbral(UMBRAL_NUEVO, 2)} if nombre == 'parada' else {'F1_macro': 'f1_macro'}
    for fold, (tr, va) in enumerate(cv.split(), 1):
        est = clone(modelo).fit(X.iloc[tr], y.iloc[tr])
        Xva = est.named_steps['historia'].transform(X.iloc[va])
        resultado = permutation_importance(est[1:], Xva, y.iloc[va], scoring=scores,
                                          n_repeats=3, random_state=SEED, n_jobs=1)
        for metrica, valor in resultado.items():
            importancias.append(pd.DataFrame({'variable': FEATURES, 'caida': valor.importances_mean,
                                              'modelo': nombre, 'metrica': metrica, 'fold': fold}))
importancias = pd.concat(importancias, ignore_index=True)
importancias.to_csv(OUT / 'importancias_por_fold.csv', index=False)
imp = importancias.groupby(['modelo', 'metrica', 'variable']).agg(
    caida_media=('caida', 'mean'), desvio=('caida', 'std'), folds_positivos=('caida', lambda x: (x > 0).sum())).reset_index()
imp.to_csv(OUT / 'importancias_resumen.csv', index=False)
for (modelo, metrica), g in imp.groupby(['modelo', 'metrica']):
    g = g.sort_values('caida_media')
    display(g.sort_values('caida_media', ascending=False).round(4))
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(g.variable, g.caida_media, xerr=g.desvio)
    ax.axvline(0, color='black', linewidth=.8)
    ax.set(xlabel='Caída de métrica al permutar (media ± desvío entre folds)', title=f'{modelo} · {metrica}')
    guardar_figura(f'importancia_{modelo}_{metrica}')
print('Excluidas por diseño, no ignoradas por el bosque:', sorted(PROHIBIDAS))
''')
agregar('''## 6 · Conclusión generada a partir de esta corrida
Las nuevas métricas describen la cercanía a la decisión observada. No permiten
determinar si una parada alternativa habría sido mejor ni atribuir intenciones al piloto.
Para demostrar una mejora de generalización hace falta una evaluación independiente.
''', 'markdown')
agregar('''a = metricas_umbral(ypit_test, proba_test, UMBRAL_BASE)
b = metricas_umbral(ypit_test, proba_test, UMBRAL_NUEVO)
r = temporal[temporal.conjunto.eq('2025') & temporal.umbral.eq(UMBRAL_NUEVO)].set_index('tolerancia')
display(Markdown(f"""**Comparación descriptiva 2025.** Umbral {UMBRAL_BASE:.3f} → {UMBRAL_NUEVO:.3f}:
recall {a['recall']:.1%} → {b['recall']:.1%}; precisión {a['precision']:.1%} → {b['precision']:.1%};
FP {a['FP']} → {b['FP']}; FN {a['FN']} → {b['FN']}.

Con el nuevo umbral, cobertura exacta {r.loc[0, 'cobertura_paradas']:.1%}; con anticipación de hasta
3 vueltas {r.loc[3, 'cobertura_paradas']:.1%}. La precisión por episodios con esa tolerancia es
{r.loc[3, 'precision_episodios']:.1%}. No es intercambiable con la precisión por vuelta.
"""))
versiones = {'numpy': np.__version__, 'pandas': pd.__version__, 'sklearn': sklearn.__version__,
            'umbral_base': UMBRAL_BASE, 'umbral_nuevo': UMBRAL_NUEVO, 'regla': 'maximo F2 OOF; empate mayor umbral; candidatos <= 0.475'}
(OUT / 'ejecucion.json').write_text(json.dumps(versiones, indent=2), encoding='utf-8')
print('Tablas y figuras:', OUT.resolve())
''')
nb = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': copy.deepcopy(base['metadata']), 'cells': cells}
for i, cell in enumerate(cells):
    cell['id'] = f'correcciones-{i:03d}'
(HERE / 'Entrega3_F1_v7_correcciones.ipynb').write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding='utf-8')
print('Notebook de correcciones generado:', len(cells), 'celdas')
