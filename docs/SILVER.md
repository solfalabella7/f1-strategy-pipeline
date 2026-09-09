# Silver: primera sesión

La primera ejecución procesa únicamente Austria 2024, `session_key=9550`.
La entrada es exclusivamente `include/output/bronze/`; no se consulta OpenF1 y
no se modifica ningún archivo Bronze. El resultado queda en
`include/output/silver/season=2024/session=9550/`.

## Contrato

`laps.json` tiene una fila por `session_key + driver_number + lap_number` y
usa `laps` como tabla base. Las columnas de identificación, sesión, piloto y
vuelta son copias de Bronze o joins estructurales. Las columnas de calidad,
edad temporal, `tyre_age`, `has_*`, estados y `possible_early_exit` son
derivadas.

Los stints se asignan con intervalos semiabiertos: el siguiente `lap_start` es
el límite exclusivo. Cuando hay dos stints con el mismo inicio, el primero no
recibe esa vuelta y el último intervalo iniciado prevalece. Un stint sin
`lap_start` nunca se asigna. Un último stint sin `lap_end` se extiende hasta la
última vuelta observada y se marca `open_ended`.

Weather e intervals usan el registro anterior más reciente (`date <=
lap_date_start`) y una tolerancia de 120 segundos. Position conserva el último
valor anterior aunque supere 120 segundos; `position_available`,
`position_missing`, `position_stale` y `position_timestamp_age_seconds` dejan
la antigüedad explícita. Con timestamp de vuelta nulo no se hace ningún join
temporal. `interval_raw` y `gap_to_leader_raw`
conservan el valor Bronze; la conversión numérica rechaza strings vacíos,
semánticos y desconocidos, sin convertirlos a cero.

La ausencia de resultados de pit se representa con `pit_data_available=false`
y `pit_stop=null`; la ausencia de una fila dentro de un archivo disponible es
`pit_stop=false`. No se calcula `change_tire`, `recommended_compound` ni
ningún target.

Race control se acumula sólo con eventos anteriores a la vuelta por timestamp,
o por `lap_number` cuando falta el timestamp; ese fallback queda marcado como
`race_control_join_status=lap_number_fallback`. VSC y Safety Car físico tienen
señales separadas. El alcance de las amarillas se conserva en
`yellow_flag_scope`, `CHEQUERED FLAG` no se interpreta como roja y los eventos
globales (`driver_number=null`) se incluyen.

## Ejecución y validación

Desde la raíz del repositorio, la sesión de validación se puede ejecutar con:

```text
python -m src.silver_pipeline --season 2024 --session-key 9550
```

El comando escribe `laps.json` y `validation.json`. La etapa se detiene aquí;
no hay un loop de escalado a las 70 carreras.

Una vez aprobada la sesión de validación, el lote completo se ejecuta
explícitamente con:

```text
python -m src.silver_pipeline --all
```

Esto procesa las sesiones existentes bajo Bronze, escribe un `laps.json` y un
`validation.json` por sesión, y genera `include/output/silver/global_validation.json`
y `include/output/silver/anomalies.json`. Los reportes distinguen anomalías
reales de fuentes Bronze ausentes esperadas; no consultan OpenF1.