# Correcciones de la Entrega 3

El notebook `Entrega3_F1_v7_correcciones.ipynb` es un complemento autocontenido de
la v6 centrado en `CorreccionesEntrega3.md`. La v6 conserva la comparación de
familias, ajuste y ablaciones originales. No se modifican materiales de Entrega 4.

| Devolución | Implementación |
|---|---|
| Recall en X, precisión en Y, umbrales dentro del gráfico | Sección 1: curva precisión–recall OOF con puntos anotados |
| Bajar umbral y revisar cuántas paradas se recuperan | Selección por máximo F2 OOF entre umbrales de 0,025 a 0,475; desempate por mayor umbral |
| Rehacer matrices de confusión | Sección 2: conteos y normalizaciones por fila y columna, tanto OOF como 2025 |
| Ver todas las vueltas con parada y los FP | CSV completos por umbral, con claves de carrera, piloto y vuelta |
| Matizar falsos positivos por distancia | Sección 3: categorías 1, 2–3, 4–10, >10 vueltas y sin parada posterior observada |
| Comparar tolerancia de 1 a 3 vueltas | Cobertura por parada, fracción de alarmas cercanas y precisión/recall por episodios para k=0,1,2,3 |
| Mostrar errores entendibles y especiales | Sección 4: selección determinística de casos y trayectorias completas, más perfil VP/FN |
| Qué features usa/ignora el random forest | Sección 5: permutación por fold para ambos bosques; en parada se usa explícitamente el umbral de cada criterio |

## Criterios de interpretación

- Una alarma cercana sigue siendo FP para la etiqueta de vuelta exacta.
- Una racha termina al dejar de alertar, faltar una vuelta consecutiva o registrarse
  una parada. El emparejamiento episodio/parada es uno a uno y no cruza piloto ni carrera.
- La cobertura por ventana puede contar alarmas repetidas para una parada, pero esa
  parada se cuenta una sola vez. La precisión por episodios penaliza episodios sobrantes.
- Las distancias se calculan hacia la próxima parada; una alarma posterior no anticipó
  la parada anterior. Los casos sin parada posterior quedan separados, sin distancia imputada.
- El final de observación no permite distinguir por sí solo stint final, retiro o
  datos incompletos. Se informa cuántas vueltas posteriores se observaron.
- Cercanía temporal no demuestra conveniencia estratégica ni intención del piloto.
- Importancia baja no demuestra que el bosque ignore una variable: puede haber
  redundancia. Las ablaciones de la v6 complementan esta lectura.
- Se conserva la referencia histórica 0,475. F2 es un nuevo criterio, explícito y
  fijado antes de ejecutar; no se oculta su costo en falsas alarmas.
- 2025 se usa descriptivamente: ya fue examinado. Los resultados OOF reutilizan
  folds empleados previamente para seleccionar modelos y no son una validación
  independiente de todo el procedimiento de selección.

## Reproducción

Desde la raíz del repositorio, con el entorno de análisis instalado:

```powershell
.venv/Scripts/python.exe Entrega3/construir_correcciones.py
.venv/Scripts/python.exe Entrega3/verificar_correcciones.py --ejecutar
```

El primer comando regenera el notebook y elimina sus salidas anteriores. El segundo
ejecuta las pruebas temporales, valida estructura y sintaxis, ejecuta el notebook y
conserva sus salidas. Sin `--ejecutar` solo realiza las comprobaciones.

`analisis_correcciones.py` contiene las funciones de evaluación; el generador las
incluye en el notebook para que este no dependa de importar módulos locales en Colab.
Se reutilizan sin cambios las celdas de preparación e historia causal de la v6.
Los CSV se buscan en las ubicaciones originales; si faltan, se conserva el mecanismo
original de descarga. La ejecución local utiliza los CSV Silver presentes.

Las tablas y figuras quedan en `Entrega3/resultados_correcciones/`. `ejecucion.json`
registra versiones y umbral elegido. Las versiones pueden diferir de scikit-learn
1.6.1 usado originalmente y deben citarse junto con los resultados recalculados.

## Lectura de la comparación ejecutada

Con las dependencias actuales, F2 OOF selecciona **0,475**, igual que la referencia.
No se fuerza un umbral inferior después de ver ese resultado. Se muestran igualmente
las alternativas solicitadas, incluyendo sus errores completos:

| Umbral | Recall 2025 | Precisión 2025 | VP | FP | FN |
|---|---:|---:|---:|---:|---:|
| 0,300 | 71,4 % | 4,7 % | 573 | 11.598 | 229 |
| 0,400 | 62,8 % | 5,9 % | 504 | 8.066 | 298 |
| 0,450 | 58,1 % | 6,6 % | 466 | 6.635 | 336 |
| 0,475 | 54,9 % | 6,9 % | 440 | 5.982 | 362 |
| 0,500 | 51,9 % | 7,5 % | 416 | 5.096 | 386 |

Por ejemplo, pasar de 0,475 a 0,400 detecta 64 paradas adicionales a cambio de
2.084 falsas alarmas adicionales. Esto muestra por qué aumentar recall no basta
para concluir que el sistema mejora. 2025 se analiza descriptivamente y no se usa
para elegir otro umbral. Los conteos recalculados no sustituyen silenciosamente
los guardados en la v6: corresponden al entorno registrado en esta nueva corrida.

## Verificación realizada

- Notebook ejecutado completo: 15 celdas de código con salidas guardadas, sin errores.
- Cinco pruebas de casos temporales aprobadas; estructura y sintaxis válidas.
- Revisados visualmente curva precisión–recall, matrices, distribución de distancias,
  cobertura por tolerancia e importancia de variables.
- Entorno de esta corrida: NumPy 2.5.4, pandas 3.1.1, scikit-learn 1.9.1.
- Se adaptó la extracción de variables para permutación a la API actual accediendo
  directamente al transformador `historia`, sin alterar su cálculo causal.
