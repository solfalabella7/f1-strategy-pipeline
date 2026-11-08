"""Evaluación descriptiva de alarmas, sin modificar etiquetas ni entrenar modelos."""
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score, fbeta_score

CLAVES_EVALUACION = ['session_key', 'driver_number', 'lap_number']


def auditar_alarmas(datos, probabilidades, umbral):
    tabla = datos.copy().reset_index(drop=True)
    if tabla.duplicated(CLAVES_EVALUACION).any():
        raise ValueError('La evaluación exige una fila por piloto, carrera y vuelta')
    if tabla.pit_stop.isna().any():
        raise ValueError('No se pueden evaluar etiquetas ausentes')
    p = np.asarray(probabilidades, dtype=float)
    if len(p) != len(tabla) or not np.isfinite(p).all():
        raise ValueError('Puntajes ausentes o desalineados')
    tabla['puntaje'] = p
    tabla['alarma'] = p >= umbral
    tabla['real'] = tabla.pit_stop.astype(bool)
    tabla['distancia_proxima_parada'] = np.nan
    tabla['desde_parada_anterior'] = np.nan
    tabla['vueltas_observadas_restantes'] = 0
    for _, g in tabla.groupby(['session_key', 'driver_number']):
        laps = g.lap_number.to_numpy()
        pits = np.sort(g.loc[g.real, 'lap_number'].to_numpy())
        tabla.loc[g.index, 'vueltas_observadas_restantes'] = laps.max() - laps
        if len(pits):
            siguiente = np.searchsorted(pits, laps, side='right')
            anterior = np.searchsorted(pits, laps, side='left') - 1
            dprox = np.full(len(g), np.nan)
            dprev = np.full(len(g), np.nan)
            hay_proxima, hay_anterior = siguiente < len(pits), anterior >= 0
            dprox[hay_proxima] = pits[siguiente[hay_proxima]] - laps[hay_proxima]
            dprev[hay_anterior] = laps[hay_anterior] - pits[anterior[hay_anterior]]
            tabla.loc[g.index, 'distancia_proxima_parada'] = dprox
            tabla.loc[g.index, 'desde_parada_anterior'] = dprev
    tabla['tipo'] = np.select([tabla.real & tabla.alarma, ~tabla.real & tabla.alarma,
                               tabla.real & ~tabla.alarma], ['VP', 'FP', 'FN'], default='VN')
    d = tabla.distancia_proxima_parada
    tabla['categoria_fp'] = np.select(
        [tabla.tipo.ne('FP'), d.eq(1), d.between(2, 3), d.between(4, 10), d.gt(10)],
        ['no es FP', '1 vuelta', '2–3 vueltas', '4–10 vueltas', '>10 vueltas'],
        default='sin parada posterior observada')
    # Un episodio se corta también al parar: no puede atravesar dos stints.
    episodios, paradas = [], []
    for (sesion, piloto), g in tabla.groupby(['session_key', 'driver_number']):
        g = g.sort_values('lap_number')
        actual = []
        def cerrar():
            if actual:
                episodios.append({'session_key': sesion, 'driver_number': piloto,
                                  'inicio': actual[0], 'fin': actual[-1], 'duracion': len(actual)})
                actual.clear()
        for r in g.itertuples():
            if actual and (not r.alarma or r.lap_number != actual[-1] + 1):
                cerrar()
            if r.alarma:
                actual.append(r.lap_number)
            if r.real:
                cerrar()
                fila = {'session_key': sesion, 'driver_number': piloto, 'lap_number': r.lap_number,
                        'puntaje': r.puntaje, 'detectada_exacta': r.alarma}
                for k in range(4):
                    fila[f'aviso_0a{k}'] = bool((g.alarma & g.lap_number.between(r.lap_number-k, r.lap_number)).any())
                paradas.append(fila)
        cerrar()
    ep = pd.DataFrame(episodios, columns=['session_key', 'driver_number', 'inicio', 'fin', 'duracion'])
    reales = pd.DataFrame(paradas, columns=CLAVES_EVALUACION + ['puntaje', 'detectada_exacta'] + [f'aviso_0a{k}' for k in range(4)])
    return tabla, ep, reales


def emparejar_episodios(episodios, reales, tolerancia):
    """Asociación cronológica uno a uno; no cruza piloto/carrera ni premia avisos posteriores."""
    usados = set()
    coincidencias = 0
    for p in reales.sort_values(CLAVES_EVALUACION).itertuples():
        candidatos = episodios[(episodios.session_key == p.session_key) &
                               (episodios.driver_number == p.driver_number) &
                               (episodios.inicio <= p.lap_number) &
                               (episodios.fin >= p.lap_number - tolerancia) &
                               (~episodios.index.isin(usados))]
        if len(candidatos):
            elegido = candidatos.sort_values(['fin', 'inicio']).index[0]
            usados.add(elegido)
            coincidencias += 1
    return coincidencias


def metricas_umbral(y, p, umbral):
    pred = np.asarray(p) >= umbral
    vn, fp, fn, vp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {'umbral': umbral, 'VP': vp, 'FP': fp, 'FN': fn, 'VN': vn,
            'precision': precision_score(y, pred, zero_division=0),
            'recall': recall_score(y, pred, zero_division=0),
            'F1': f1_score(y, pred, zero_division=0),
            'F2': fbeta_score(y, pred, beta=2, zero_division=0),
            'alarmas_cada_100_vueltas': 100 * pred.mean()}


def resumen_temporal(tabla, episodios, reales):
    filas = []
    for k in range(4):
        aciertos = emparejar_episodios(episodios, reales, k)
        cercanas = tabla.alarma & (tabla.real | tabla.distancia_proxima_parada.le(k))
        filas.append({'tolerancia': k,
                      'cobertura_paradas': reales[f'aviso_0a{k}'].mean() if len(reales) else np.nan,
                      'fraccion_alarmas_cercanas': cercanas.sum()/tabla.alarma.sum() if tabla.alarma.any() else np.nan,
                      'episodios_emparejados': aciertos,
                      'precision_episodios': aciertos/len(episodios) if len(episodios) else np.nan,
                      'recall_episodios': aciertos/len(reales) if len(reales) else np.nan,
                      'episodios_sin_asociar': len(episodios)-aciertos})
    return pd.DataFrame(filas)
