# Diccionario de datos para la decisión

## Unidad y momento

Una fila representa una vuelta registrada de un piloto en una carrera. La clave es `(session_key, driver_number, lap_number)`. El instante `decision_timestamp` se calcula como `lap_date_start + lap_duration`; representa el cierre de la vuelta y el conocimiento disponible antes de la vuelta siguiente.

## Variables principales

| Campo | Fuente | Significado | Uso |
|---|---|---|---|
| `current_compound` | stints | Compuesto usado durante la vuelta | predictor |
| `tyre_age` / `decision_tyre_age` | stints + vuelta | Edad al iniciar / tras completar la vuelta | predictor |
| `pit_stop` | pit | Hubo evento de pit en la vuelta | diagnóstico; no predictor del mismo horizonte |
| `accion_observada_proxima_vuelta` | pits + stints | `CONTINUAR` o compuesto que se monta en la próxima vuelta | objetivo |
| `decision_air_temperature`, `decision_track_temperature`, `decision_humidity`, `decision_rainfall` | weather as-of | Clima más reciente anterior al cierre de vuelta | predictor |
| `decision_position`, `decision_interval`, `decision_gap_to_leader` | position / intervals as-of | Situación competitiva más reciente anterior | predictor |
| `decision_safety_car`, `decision_virtual_safety_car`, `decision_yellow_flag`, `decision_red_flag` | race_control as-of | Estado de pista al cierre de vuelta | predictor/diagnóstico |
| `pace_last_3`, `pace_delta_last_3` | laps anteriores | Mediana y cambio del ritmo de las últimas vueltas utilizables | predictor |
| `decision_eligible` | derivada | La fila tiene instante, estado y neumático utilizables | filtro |
| `target_available` | derivada | La acción siguiente está confirmada | filtro |
| `target_exclusion_reason` | derivada | Motivo por el que el objetivo queda nulo | diagnóstico |

## Reglas temporales

Las uniones `weather`, `position`, `intervals` y `race_control` seleccionan el registro anterior más reciente. Nunca se usa una fecha posterior a `lap_date_start` o `decision_timestamp`. Clima e intervalos deben estar dentro de 120 segundos; posición conserva el último estado y expone su antigüedad. Una etiqueta puede usar información posterior a la decisión únicamente como resultado observado para supervisión, nunca como predictor.

## Nulos

Un nulo puede significar que la variable no aplica, que la fuente no entregó registros, que no existía una observación anterior válida, que se superó la tolerancia temporal o que la acción siguiente no pudo confirmarse. Los reportes contabilizan cada motivo; no se reemplazan desconocidos por cero.

## Predictores permitidos

La lista canónica está en `src/decisions.py::FEATURES`: `lap_number`, edad del neumático, ritmo histórico, clima, posición, gaps, estados de pista, circuito y compuesto actual. Se excluyen explícitamente el pit objetivo, el compuesto siguiente, los resultados finales y variables construidas mirando el final de la sesión.
