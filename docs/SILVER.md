# Silver: Especificación y Contratos de Datos

El pipeline procesa los datos crudos almacenados bajo `include/output/bronze/` de forma 100% determinística y sin conexión a internet ni llamadas a la API de OpenF1.

La capa Silver genera **dos datasets consolidados complementarios** y sus correspondientes archivos por sesión:

1. **Dataset Principal de Vueltas (`f1_silver_dataset.csv` / `laps.json` / `laps.csv`)**:
   - **Unidad de análisis:** 1 fila = 1 vuelta de un piloto en una carrera.
   - **Clave primaria:** `(session_key, driver_number, lap_number)`.
   - **Volumen:** 77.373 filas y 89 columnas (0 duplicados).

2. **Dataset Específico de Paradas en Boxes (`f1_silver_pit_stops.csv` / `pit_stops.json` / `pit_stops.csv`)**:
   - **Unidad de análisis:** 1 fila = 1 parada en boxes de un vehículo en una carrera.
   - **Clave primaria:** `(session_key, driver_number, lap_number, pit_index)`.
   - **Volumen:** 2.333 filas y 93 columnas (0 no-pits, 0 duplicados).
   - **Columna clave resuelta:** `new_compound` (compuesto montado tras la parada, determinado emparejando la parada con el stint de salida sin copiar el compuesto previo ni asumir cambios arbitrarios).

---

## Contrato del Dataset de Vueltas (`laps.json`)

`laps.json` tiene una fila por `session_key + driver_number + lap_number` y usa `laps` como tabla base. Las columnas de identificación, sesión, piloto y vuelta son copias de Bronze o joins estructurales. Las columnas de calidad, edad temporal, `tyre_age`, `has_*`, estados y `possible_early_exit` son derivadas.

Los stints se asignan con intervalos semiabiertos: el siguiente `lap_start` es el límite exclusivo. Cuando hay dos stints con el mismo inicio, el primero no recibe esa vuelta y el último intervalo iniciado prevalece. Un stint sin `lap_start` nunca se asigna. Un último stint sin `lap_end` se extiende hasta la última vuelta observada y se marca `open_ended`.

Weather e intervals usan el registro anterior más reciente (`date <= lap_date_start`) y una tolerancia de 120 segundos. Position conserva el último valor anterior aunque supere 120 segundos; `position_available`, `position_missing`, `position_stale` y `position_timestamp_age_seconds` dejan la antigüedad explícita. Con timestamp de vuelta nulo no se hace ningún join temporal. `interval_raw` y `gap_to_leader_raw` conservan el valor Bronze; la conversión numérica rechaza strings vacíos, semánticos y desconocidos, sin convertirlos a cero.

La ausencia de resultados de pit se representa con `pit_data_available=false` y `pit_stop=null`; la ausencia de una fila dentro de un archivo disponible es `pit_stop=false`.

Race control se acumula sólo con eventos anteriores a la vuelta por timestamp, o por `lap_number` cuando falta el timestamp; ese fallback queda marcado como `race_control_join_status=lap_number_fallback`. VSC y Safety Car físico tienen señales separadas. El alcance de las amarillas se conserva en `yellow_flag_scope`, `CHEQUERED FLAG` no se interpreta como roja y los eventos globales (`driver_number=null`) se incluyen.

---

## Contrato del Dataset de Paradas en Boxes (`pit_stops.json`)

`pit_stops.json` contiene exclusivamente eventos donde `pit_stop == True`. Se resuelve mediante la función determinística `resolve_driver_pits`:
- Empareja cada parada en boxes $P_j$ del piloto con su stint entrante ($S_j$) y su stint saliente ($S_{j+1}$).
- Tolera las variaciones de indexación de OpenF1 entre temporadas (en 2023 `lap_start` del nuevo stint inicia en la vuelta de pit $L$, mientras que en 2024 inicia en $L+1$).
- Resuelve con 100% de cobertura:
  - `current_compound`: Compuesto con el que el piloto entró a boxes.
  - `new_compound`: Compuesto nuevo montado tras el cambio de neumáticos.
  - `stint_in_number` y `new_stint_number`: Números de tanda antes y después de la parada.
  - `stint_in_tyre_age`: Vueltas acumuladas por el neumático saliente.
  - Tiempos de parada (`pit_duration`, `stop_duration`).

---

## Ejecución y Validación

Desde la raíz del repositorio:

* **Procesar una sesión específica (ej. Gran Premio de Austria 2024, sesión 9550):**
  ```bash
  python -m src.silver_pipeline --season 2024 --session-key 9550
  ```
  Genera `laps.json`, `laps.csv`, `pit_stops.json`, `pit_stops.csv` y `validation.json` en `include/output/silver/season=2024/session=9550/`.

* **Procesar todas las sesiones disponibles en Bronce (70 carreras):**
  ```bash
  python -m src.silver_pipeline --all
  ```
  Genera la capa Silver para cada sesión junto con `f1_silver_dataset.csv`, `f1_silver_pit_stops.csv`, `global_validation.json` y `anomalies.json`.

* **Verificar los 7 Criterios de Calidad de la Cátedra:**
  ```bash
  python verify_quality_criteria.py
  ```