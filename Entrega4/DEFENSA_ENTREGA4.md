# Guía de defensa · Entrega 4 · Visualización y app

**Grupo 5K10-10** · Castillo, Expósito, Epifani, Falabella, Farías y Camacho
**App:** «Ventana de boxes». Antes de entrar, abrí la URL pública de GitHub Pages en el navegador y el repositorio en GitHub con el README.

> La evaluación es individual y las preguntas son dirigidas: **todos tienen que poder contestar todo**. Ensayar con cronómetro. Antes de entrar, abrir la URL desde **otra computadora o desde el celular**: que ande en la notebook de uno no alcanza.

Todos los números de esta guía salen de `Entrega4/artefactos/construccion.json`, la última corrida de `build_app.py`, y coinciden con el notebook v6.

---

## 0:00–2:00 · Qué cambió desde la Entrega 3 (dos oraciones)

> «El modelo es el mismo de la Entrega 3: dos random forest, uno decide si para y otro qué neumático monta, con umbral 0,475. Lo que corregimos fue la lectura de los errores, como nos pidieron: curva precisión–recall con los umbrales rotulados, falsas alarmas según cuántas vueltas faltaban para la parada, tolerancia de 1 a 3 vueltas e importancia del bosque sin permutación. La regla nueva por F2, que premia el recall, da 0,40 con las versiones de la v6 y 0,475 con las de la v7. La curva es casi plana; mantuvimos 0,475 y mostramos lo que cambia con 0,40: 73 paradas más anticipadas y 2.380 falsas alarmas más.»

Si preguntan por qué no 0,40: «0,475 es el umbral con el que se evaluó el test una sola vez. Elegir otro después de mirar 2025 sería usar el test para decidir. La diferencia de F2 entre los dos es menor que la que produce cambiar de versión de scikit-learn».

Si preguntan por el detalle, está en el desplegable del modelo, tabla «Qué corregimos desde la Entrega 3».

## 2:00–10:00 · El tallo (de la portada al modelo, en orden)

| Sección | Título (lo que afirma) | Número que lo sostiene |
|---|---|---|
| Portada | El modelo detecta cuándo se abre la ventana de parada, pero no ve venir las paradas que provocan el safety car y la lluvia | 65 % de las paradas en seco y sin safety car con alarma (433/663); 5 % de las con safety car o lluvia (7/139); 70 % de las rachas de alarma terminan en parada (452/641). Todo en 2025 |
| 01 Los datos | Solo 3 de cada 100 vueltas terminan en boxes, y las grandes tandas de paradas llegan con safety car o lluvia | 2.333 paradas en 70.746 vueltas (3,3 %). Cuando paran 10 o más autos en la misma vuelta, en el 60 % de los casos hay safety car o lluvia; las paradas en solitario, solo en el 5 % |
| 02 Lo que encontramos | Con safety car los equipos cambian de plan: en seco, el HARD baja del 54 % al 36 % | Brecha 0,187 en seco; 0,246 sobre todas las paradas (verde) |
| 03 El modelo | Anticipa 2 de cada 3 paradas en seco, pero casi ninguna de las que provocan el safety car o la lluvia | 65 % contra 5 % (safety car) y 6 % (lluvia) |

**Por qué el hilo es ese:** la devolución de la Entrega 3 pidió mirar en qué se equivoca el modelo y qué le resulta fácil y qué difícil. Lo fácil son las paradas planificadas (un neumático que se gasta). Lo difícil son las reactivas, justo las que provoca el safety car, que el modelo no puede ver: quedó fuera por la devolución de la Entrega 2. El dato (01), el hallazgo (02) y el modelo (03) cuentan la misma historia.

## 10:00–15:00 · La copa (el docente toma el mouse)

**Qué componente del gráfico toca cada control.** Los parámetros están declarados en Altair (`alt.param`); el control solo les cambia el valor:

| Control | Parámetro | Componente que toca |
|---|---|---|
| Temporada | `temporada` | **Transformación**: `transform_filter` del panorama |
| Tipo de parada | `contexto` | **Transformación**: `transform_filter` del panorama |
| Umbral | `umbral` | **Transformación** (`calculate` de «con alarma / sin alarma» en el panorama) y **mapeo** (`condition` del color en el mapa y la regla de la trayectoria) |
| Gran Premio | — | **Datos**: carga `datos/carreras/<carrera>.json` en el dato con nombre `carrera` |
| Piloto | `piloto` | **Mapeo**: `condition` de la opacidad (apaga a los demás) |
| Clic en una vuelta | `seleccion` | **Capa** del marco negro (`transform_filter` por id) y ficha de detalle |
| Pasar el mouse | — | **Mapeo**: canal `tooltip` |

**Si el docente carga un caso raro en «Probá»:**
- **Fuera del rango que vio el modelo** (2023–2024), por ejemplo edad 200: no predice y marca el campo con un mensaje («está fuera de lo que vio el modelo, 0 a 77»).
- **Combinación imposible**, por ejemplo más paradas que vueltas o llevar MEDIUM sin marcarlo como usado: tampoco predice.
- **Combinación rara pero real**, por ejemplo más compuestos usados que paradas + 1, que aparece en 149 vueltas: predice y avisa la frecuencia.
- **Categoría que el modelo no vio**, como «Racing Bulls» (nombre de 2025): no se puede elegir. Los menús solo ofrecen equipos y circuitos de 2023–2024.

**Para mostrar:**
- Bélgica 2025, piloto Albon: el mapa muestra a todo el pelotón pasando de intermedios a MEDIUM en las vueltas 11 a 13, y el modelo propone LLUVIA. Es el 0 de 26.
- «Probar esta vuelta» lleva la vuelta al formulario y da el mismo resultado.

## 15:00–22:00 · Lo que hay que saber explicar

### Un gráfico, componente por componente

**01 · Paradas por carrera**
- Datos: las 2.333 paradas agrupadas por (carrera, vuelta), una fila por vuelta con paradas, más una fila por carrera para la barra gris.
- Mapeo: x = vuelta (cuantitativa); y = carrera (nominal, ordenada por fecha); área = pilotos que paran; color = contexto.
- Marcas: círculo, más una regla gruesa gris de la vuelta 1 a la última registrada.
- Escalas: x de 0 a 80; tamaño con dominio de 1 a 20 pilotos; color con la paleta de contexto (seco pizarra, safety car ámbar, lluvia azul).
- Transformación: conteo por (carrera, vuelta) y marca de contexto (si alguna de esas paradas fue con safety car → ámbar).

**02 · Hallazgo (gráfico de mancuernas)**
- Datos: 2.106 paradas a compuestos de seco.
- Transformación: tabla cruzada normalizada por fila: cada situación suma 100 %.
- Mapeo: x = % de paradas, y = compuesto, color y forma = situación (círculo sin safety car, rombo con safety car).
- Marcas: punto, una regla que une los dos valores y un texto con el %.
- Escala: x con eje común de 0 a 60 %. Se eligió posición sobre un eje común en lugar de barras apiladas porque se comparan dos grupos por compuesto (posición > largo > área).

**03 · Modelo**
- Datos: 802 paradas reales de 2025.
- Transformación: % con alarma (puntaje ≥ 0,475) por contexto.
- Mapeo y marca: barra horizontal; x = % de 0 a 100 % (la barra codifica con su largo, por eso arranca en 0); color = contexto, con la misma paleta que en 01; texto con «% · n de N».

**Copa · Mapa de la carrera**
- Datos: todas las vueltas de la carrera, con su puntaje.
- Mapeo: x = vuelta (ordinal), y = piloto (ordenado por vueltas corridas).
- Color: condición `puntaje >= umbral`. Si se cumple, escala secuencial cian según el puntaje (más claro, más alto); si no, gris.
- Segunda capa de círculos: paradas reales, coloreadas por el compuesto montado, con la misma paleta que en todo el sitio.

**Colores (iguales en toda la app):**
- Compuesto: los colores de Pirelli. SOFT rojo, MEDIUM amarillo, HARD blanco y LLUVIA azul (en la sección clara, HARD pasa a pizarra porque el blanco no se ve).
- Contexto: seco blanco, safety car ámbar, lluvia azul.
- Modelo: **cian**, el color de la telemetría. Siempre que aparece cian es el modelo.
- Interfaz: rojo racing para la marca y los encabezados; lima para indicadores (la torre de la portada, sectores completados). Nunca se usan para datos del modelo.
- **Por qué cian y no lima:** el lima se confundía con el amarillo del MEDIUM para daltonismo (ΔE 3,7 en el validador de paletas), y en el mapa de carrera conviven los dos. El cian pasa contra los cuatro compuestos.

### Una decisión de diseño que cambiamos

1. **H1 (Entrega 2 → app):** era un boxplot de `tyre_age`. No funcionaba por dos motivos: escondía la forma de las distribuciones, y usaba la edad de la vuelta del pit, que en 321 paradas ya era 0 (fuga). Ahora es un histograma de `tyre_age_prev`, con cada grupo normalizado por separado (desplegable de 02).
2. **Umbral (Entrega 3 → app):** era un gráfico de precisión, recall y F1 contra el umbral. No dejaba ver el intercambio que pidió el docente. Ahora es una curva precisión–recall con recall en X, precisión en Y y cada umbral rotulado sobre la curva. Además:
   - En la primera versión el eje Y estaba fijo en 20 % y cortaba la curva.
   - Incluía umbrales sin alarmas, que dibujaban una caída falsa a 0 %.
   - Se corrigieron las dos cosas.
3. **Gráfico del modelo:** la primera versión tenía una barra gris «de fondo» hasta 100 % detrás de cada barra. No sumaba nada porque el eje ya llega a 100 %, y se veía como una franja clara encima de la primera barra. Se sacó.

### Cómo llega el modelo a la aplicación

1. `build_app.py` entrena los dos random forest con la configuración y la semilla de la v6 sobre la capa Silver.
2. `src/exportar_modelo.py` guarda en JSON cada parámetro aprendido: medianas del imputador, media y escala, categorías del one-hot y cada nodo de cada árbol (variable, umbral, hijos, probabilidades de las hojas).
3. `Entrega4/app/modelo.js` recorre los árboles igual que scikit-learn, incluida la conversión a float32, y promedia las hojas.
4. El build verifica con Node.js las 69.472 vueltas: la diferencia máxima es 1,6 × 10⁻¹⁵ y la clase coincide en el 100 %.

**Si preguntan «el instructivo dice un árbol, ustedes tienen un bosque»:**

> «Un bosque son 150 árboles, y la fórmula de cada uno se escribe completa en la página: no es una aproximación. Probamos que da lo mismo que `predict_proba` en todas las vueltas. Cambiar a un modelo más simple habría sido otra decisión de modelado: en la Entrega 3 la logística quedó debajo del bosque por más que el desvío (+0,039 ± 0,026 en parada, +0,049 ± 0,034 en neumático).»

En «Explorá» las predicciones no se calculan en el navegador: vienen precalculadas por el build. En 2025 son del modelo final; en 2023–2024, del modelo de validación cruzada que no vio esa carrera.

### Cómo se regenera si cambian los datos

1. Correr el pipeline: el DAG de Airflow o `python -m src.silver_pipeline --all`.
2. Correr `python build_app.py`. Entrena de nuevo con semilla 42, recalcula el umbral con la regla de la v6 y compara 20 números con el notebook: si los datos cambiaron, lista cuáles difieren.
3. Hacer commit y push de `Entrega4/sitio`. El flujo `.github/workflows/pages.yml` publica solo.

### Preguntas probables

- **¿Por qué F1 y no accuracy?** Solo el 3 % de las vueltas es parada: «nunca parar» tiene 96,9 % de accuracy y no sirve para nada.
- **¿Cuánto le gana al piso?** En parada, 0,128 contra 0,060 de «siempre parar» en test. En neumático, F1 macro 0,638 contra 0,140 de «siempre HARD».
- **¿Por qué validar por carrera?** Las vueltas de una carrera se parecen. Repartiendo filas al azar el F1 sube a 0,250 y 0,753, y ese salto es fuga.
- **¿El umbral 0,475 es mágico?** No. Sale de las predicciones fuera de pedazo de 2023–2024, con la regla de máximo F1. La curva es casi plana entre 0,45 y 0,575. Con 0,40 en 2025 se anticipan 73 paradas más (513) a cambio de 2.380 falsas alarmas más.
- **¿Las falsas alarmas son errores?** Para la etiqueta de vuelta exacta, sí. Pero el 57 % llega como mucho 10 vueltas antes de una parada real (mediana: 7 vueltas antes). De las que no tienen parada en las 10 vueltas siguientes, en el 41 % el piloto ya no vuelve a parar (stint final largo).
- **¿Qué variables usa?**
  - Con permutación (mide en carreras no vistas): para parar, edad del neumático, paradas hechas, si ya usó HARD y el compuesto; para el neumático, la vuelta y qué lleva el pelotón.
  - Sin permutación (MDI): aparecen además clima y circuito. MDI se mide sobre el entrenamiento y favorece variables con muchos valores, así que no alcanza para decir que generalizan.
- **¿Coincide con el notebook?** Sí: 20 de 20 números de control. Usamos las versiones de la v6 (scikit-learn 1.6.1). La v7 se corrió con 1.9.1 y da 5.982 falsas alarmas en lugar de 5.637.

## Reparto sugerido (para saber quién arranca cada parte, no quién responde)

| Min. | Parte | Arranca |
|---|---|---|
| 0–2 | Qué cambió | Farías |
| 2–5 | Portada y 01 Los datos | Epifani |
| 5–7,5 | 02 Lo que encontramos | Falabella |
| 7,5–10 | 03 El modelo | Castillo |
| 10–15 | Copa: acompañar al docente | Expósito y Camacho |
