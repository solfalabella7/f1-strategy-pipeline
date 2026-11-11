# Entrega 4 · Visualización y aplicación

**App:** «Ventana de boxes». Es una página estática generada por [`build_app.py`](../build_app.py) a partir de la capa Silver del pipeline y de los dos modelos elegidos en la Entrega 3 (notebook [`Entrega3_F1_v6.ipynb`](../Entrega3/Entrega3_F1_v6.ipynb)).

- **Idea central:** el modelo detecta cuándo se abre la ventana de parada, pero no ve venir las paradas que provocan el safety car y la lluvia.
- **Indicadores de la portada** (test 2025):
  - 65 % de las paradas en seco y sin safety car tuvo alarma (433 de 663).
  - 5 % de las paradas con safety car o a neumáticos de lluvia tuvo alarma (7 de 139).
  - El 70 % de las rachas de alarma termina en una parada real (452 de 641).

## Cómo verla

```powershell
# 1. Entorno (Python 3.10–3.12; las versiones son las de la v6)
py -3.12 -m venv .venv            # o: python -m uv venv --python 3.12 .venv
.venv\Scripts\python -m pip install -r requirements-app.txt

# 2. Construir (≈ 2 minutos; necesita include/output/silver y bronze del pipeline)
.venv\Scripts\python build_app.py

# 3. Abrir en el navegador (hace falta un servidor: la página carga JSON)
.venv\Scripts\python -m http.server 8765 --directory Entrega4/sitio
#    → http://127.0.0.1:8765
```

`build_app.py --seleccion` vuelve a calcular la comparación de familias, las grillas, la comparación pareada, la ablación y la importancia (≈ 12 minutos). Sin esa opción reutiliza [`artefactos/seleccion_v6.json`](artefactos/seleccion_v6.json).

**Cuando cambian los datos**, se corre el pipeline (`astro dev run dags trigger f1_strategy_pipeline` o `python -m src.silver_pipeline --all`) y después `python build_app.py`. El script vuelve a entrenar con semilla 42, recalcula el umbral con la regla de la v6 y regenera todo. También compara 20 números de control con el notebook: si los datos cambian, avisa cuáles difieren en vez de ocultarlo.

## Publicación (GitHub Pages)

1. Construir y commitear `Entrega4/sitio/` (el sitio se sube ya generado: la capa Silver no está en el repositorio).
2. En GitHub: **Settings → Pages → Source: GitHub Actions** (una sola vez).
3. Hacer push a `main`. El flujo [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) publica `Entrega4/sitio` en `https://solfalabella7.github.io/f1-strategy-pipeline/`. También se puede disparar a mano desde la pestaña *Actions*.

### Por qué HTML estático y no Streamlit

- **El modelo se puede llevar al navegador sin aproximarlo.** Son dos random forest (≈ 96 000 y 14 000 nodos) más imputación, escalado y one-hot.
  - `src/exportar_modelo.py` exporta cada parámetro aprendido a JSON y [`app/modelo.js`](app/modelo.js) los recorre igual que scikit-learn, incluida la conversión a float32 de los árboles.
  - `build_app.py` verifica con Node.js las 69 472 vueltas: la diferencia máxima con `predict_proba` es de 1,6 × 10⁻¹⁵ y la clase coincide en el 100 %.
  - Si no coincidiera, el build lo informa.
- **«Explorá» usa predicciones generadas de antemano** (las del modelo real), como pide el instructivo para esta alternativa.
- **Ventajas frente a Streamlit Community Cloud:**
  - El link es permanente y no tiene «arranque en frío»: una app de Streamlit dormida tarda en despertar.
  - No hay servidor que mantener.
  - Se tiene control total del diseño editorial.
- **El modelo de Python también queda guardado:** los `.joblib` están en [`artefactos/`](artefactos/) y se pueden cargar con `src/modelo.py`.

## Diseño

Concepto: **el centro de análisis de una escudería**. La copa de martini se recorre como un circuito.

- **El tallo son tres sectores**, cada uno con su identidad:
  - **S1 · The Data Garage:** carbono con retícula, telemetría del dataset y diagrama del pipeline.
  - **S2 · Performance Analysis:** hoja clara con franja diagonal roja; es la única sección clara, para dar variedad.
  - **S3 · Intelligence Lab:** grafito con plano técnico cian y flujo de decisión del modelo.
- **La copa es la calle de boxes:** la franja «Boxes abiertos», luego *Race Control* (Explorá) y *Strategy Simulator* (Probá).
- **La barra superior es un tablero de tiempos por sectores.** Cada sector se llena en rojo mientras se recorre y queda en lima al completarlo.
- **Tipografía:**
  - Titillium Web para títulos (display deportivo).
  - Inter para el texto.
  - JetBrains Mono para datos, etiquetas técnicas y ejes de los gráficos.
- **Movimiento:**
  - Secuencia de cinco luces de largada en la portada.
  - Contadores que llegan al número real y aparición progresiva de bloques.
  - Todo se desactiva con «reducir movimiento» del sistema operativo.
- **Imágenes:** el monoplaza de la portada y el trazado de Marina Bay los aportó el grupo y se usan con fines académicos (crédito en el pie). Si se consigue una foto de mayor resolución para la portada, alcanza con reemplazar `app/img/portada-monoplaza.webp`.

## Estructura

| Archivo | Qué hace |
|---|---|
| [`build_app.py`](../build_app.py) | Orquesta todo: datos → modelos → verificación → JSON → gráficos → página |
| [`src/modelo.py`](../src/modelo.py) | Código de la v6 pasado a un módulo: limpieza, `RegistroCarreras`, `HistoriaCausal`, población, pedazos por carrera, pipeline e hiperparámetros. Sin él, los `.joblib` no se pueden cargar fuera del notebook (pendiente 3 de `PENDIENTES.md`) |
| [`src/analisis_app.py`](../src/analisis_app.py) | Métricas de test, lectura de errores, hipótesis 1, 2 y 4 y predicciones fuera de pedazo (celdas 40–60 de la v6) |
| [`src/seleccion.py`](../src/seleccion.py) | Selección de modelos de la v6 (secciones 4, 5, 6, 8 y 11) |
| [`src/graficos.py`](../src/graficos.py) | Todos los gráficos, en Altair, con una paleta única |
| [`src/exportar_modelo.py`](../src/exportar_modelo.py) | Exporta los bosques a JSON y verifica la paridad con Node.js |
| [`app/`](app/) | Plantilla HTML (Jinja2), estilos, lógica (`app.js`) e inferencia (`modelo.js`) |
| [`sitio/`](sitio/) | **Salida generada** (no editar a mano): `index.html` y `datos/` (modelos, paradas y una carpeta por carrera) |
| [`artefactos/`](artefactos/) | `.joblib` de los dos modelos, `seleccion_v6.json` y `construccion.json` (versiones, comparación con la v6, paridad y métricas) |
| [`../tests/test_app.py`](../tests/test_app.py) | Pruebas: puntajes publicados = `predict_proba` del `.joblib`; `modelo.js` = scikit-learn; `HistoriaCausal` sin futuro; build = v6 |

## Cumplimiento del instructivo

| Requisito | Dónde |
|---|---|
| Portada: nombre, pregunta, idea central con sujeto y verbo, tres indicadores | Portada |
| **01 Los datos:** título que afirma, gráfico, qué mirar | Gráfico de cada parada por carrera y vuelta |
| «Cómo lo sabemos»: fuente, obtención, fecha, qué es una fila, filtros en orden con cantidades antes y después, justificación, columnas descartadas por fuga | Desplegable de 01 |
| **02 Lo que encontramos:** hallazgo, gráfico, explicación | H4: con safety car baja el HARD (54 % → 36 % en seco) |
| Hipótesis que se sostuvo y que no, con números; construcción del gráfico; transformaciones | Desplegable de 02 (H4 verde, H2 roja, H1 corregida con histograma) |
| **03 El modelo:** qué logró, gráfico, explicación | Paradas anticipadas según el contexto |
| Métrica y justificación, piso, validación, comparación con media ± desvío, ajuste, test, análisis de errores, variables | Desplegable de 03 |
| **04 Explorá:** panorama, todos los registros, ≥ 2 controles que filtran de verdad, detalle de cada registro con el resultado del modelo | Temporada, tipo de parada, umbral, Gran Premio y piloto; mapa piloto × vuelta con tooltip y ficha al hacer clic |
| **05 Probá el modelo:** ingreso de valores, validación, rechazo de valores no vistos, mensajes, predicción y probabilidades | Dos modos: «Vuelta real» (carrera, piloto y vuelta a vuelta: predicción contra lo que pasó, con juicio de acierto) y «Mi escenario» (formulario con rangos de 2023–2024 y reglas de coherencia); en ambos, puntaje contra umbral y probabilidad de cada neumático |
| Gráficos en Altair, colores coherentes, tallo legible sin interacción, copa interactiva | `src/graficos.py`; paleta validada con el validador de paletas: compuestos, contexto y cian del modelo |
| Reproducible, script de construcción, README y dependencias | `build_app.py`, este archivo, `requirements-app.txt` |

**Correcciones de la Entrega 3** (`CorreccionesEntrega3.md`): la tabla «Qué corregimos desde la Entrega 3», al principio del desplegable del modelo, responde cada punto. Incluye la curva precisión–recall con umbrales rotulados, umbrales más bajos en 2025, las falsas alarmas por distancia a la parada, la tolerancia de 1 a 3 vueltas y la importancia sin permutación (MDI) junto a la de permutación.

**Defensa:** guía de los 25 minutos en [`DEFENSA_ENTREGA4.md`](DEFENSA_ENTREGA4.md).

La devolución de la Entrega 3 pedía mirar en qué forma se equivoca el modelo y qué le resulta fácil y qué difícil. Eso se tomó como eje del relato: el gráfico del modelo separa las paradas planificadas de las reactivas, y el desplegable detalla las falsas alarmas por distancia a la parada, las rachas, el perfil de las paradas omitidas y el caso de Bélgica 2025.

## Verificación realizada

- `build_app.py` reproduce la v6 (scikit-learn 1.6.1):
  - **20 de 20 números de control coinciden**, incluidos el umbral 0,475, la matriz 2025 (19 348 / 5 637 / 362 / 440), el F1 macro de compuesto 0,638, las 342 paradas con las dos decisiones correctas y las 641 rachas.
  - La selección recalculada coincide con las tablas del notebook: familias, grillas, +0,039 ± 0,026 y +0,049 ± 0,034, ablación e importancias.
- Modelo del navegador contra scikit-learn: diferencia máxima 1,6 × 10⁻¹⁵ en 69 472 vueltas.
- Pruebas: `python -m pytest tests/test_app.py tests/test_silver_pipeline.py` (13 pruebas, todas pasan; `tests/dags` corre con `astro dev pytest`).
- Navegador (Chrome, con Playwright), en escritorio de 1440 px y en móvil de 390 px:
  - Sin desborde horizontal; todos los gráficos se dibujan y ningún rótulo queda cortado.
  - Los filtros cambian los conteos: 2025 da 440 de 802 y coincide con la sección del modelo.
  - El clic en una vuelta abre su ficha y «Probar esta vuelta» la abre en el simulador.
  - Los valores fuera de rango y las combinaciones imposibles se rechazan con un mensaje.

## Inconsistencias encontradas y cómo se resolvieron

1. **`PENDIENTES.md` describe la primera versión** (regresión logística, solo `new_compound`, F1 0,503 / 0,651). Lo que se entregó y defendió es la **v6**: dos random forest, parada y compuesto (`DEFENSA_ENTREGA3.md`: «Se entrega y se presenta sólo el v6»). La app usa la v6, y la v7 de correcciones confirma su umbral.
2. **La v7 se corrió con scikit-learn 1.9.1** y sus conteos de 2025 difieren un poco de la v6: 5 982 falsas alarmas contra 5 637, con las mismas 440 paradas detectadas. Para que la app coincida con el notebook entregado se fijaron las versiones de la v6.
3. **No existía `f1_silver_pit_stops.csv` local.** Se reconstruye desde la capa Bronce con `resolve_driver_pits` del pipeline, como hacía la v6 desde la API. El resultado da las mismas 2 333 paradas y los mismos números.
4. En el formulario, tres combinaciones que parecían imposibles aparecen en datos reales, en pocas vueltas: más compuestos usados que paradas + 1, el compuesto del piloto ausente en el conteo del pelotón y edades de neumático altas. Se avisan sin bloquear, con su frecuencia.

## Límites que la app declara

- Los puntajes del bosque no son probabilidades calibradas.
- 2025 ya había sido mirado por versiones anteriores del grupo.
- El safety car está fuera del modelo por la devolución de la Entrega 2.
- Las predicciones de «Explorá» para 2023–2024 vienen de los modelos de cada pedazo de validación: el umbral se eligió con esas mismas predicciones, así que son algo optimistas.
- Las mejoras de datos de `PENDIENTES.md` (juegos de neumáticos disponibles, nominación de Pirelli) no se implementaron: cambiarían los resultados científicos y el instructivo pide usar el modelo elegido en la Entrega 3.

## Decisión del grupo: se mantiene el umbral 0,475

Ejecutando `Entrega3_F1_v7_correcciones.ipynb` con las versiones de la v6 (scikit-learn 1.6.1), los números de 2025 coinciden exactamente con la app: 440 / 5.637 / 362 con 0,475, las mismas distancias de las falsas alarmas y la misma cobertura. Pero la regla F2 de la corrección elige **0,40** (F2 0,2441 contra 0,2358). La corrida guardada de la v7, con scikit-learn 1.9.1, elegía 0,475.

- **Se mantiene 0,475 (decisión tomada):** es el umbral de la Entrega 3 y con el que se evaluó el test una sola vez. La desventaja es que la regla F2 escrita en la corrección, en este entorno, no lo elige.
- **Pasar a 0,40:** aplica la regla F2 tal como está escrita y responde a «bajar el umbral para mejorar el recall».
  - En 2025: recall 64,0 % contra 54,9 % y precisión 6,0 % contra 7,2 %.
  - Supone 73 paradas más anticipadas a cambio de 2.380 falsas alarmas más.
  - Cambian la portada y el gráfico del modelo, y habría que volver a ejecutar la v7 con estas versiones para que el notebook guardado coincida.
