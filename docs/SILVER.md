# Contrato de la capa Silver

Silver se construye exclusivamente desde los archivos Bronce inmutables y no consulta OpenF1. La unidad de análisis es una vuelta registrada de un piloto en una carrera, identificada por `session_key + driver_number + lap_number`.

## Salidas

Cada release validada contiene `f1_silver_dataset.csv`, `laps.json`, `quality.json`, `global_validation.json`, `anomalies.json` y `manifest.json`. `include/output/silver/current.json` señala la release vigente. Las releases se generan con:

```bash
python -m src.silver_pipeline --all
```

También puede procesarse una sesión aislada para depuración:

```bash
python -m src.silver_pipeline --season 2024 --session-key 9550
```

## Transformaciones

Los stints se asignan con intervalos semiabiertos; cuando hay inicios compartidos prevalece el último stint iniciado. Weather e intervals usan el registro anterior más reciente con una tolerancia de 120 segundos. Position conserva el último valor anterior y expone su antigüedad. Las uniones temporales nunca seleccionan eventos posteriores al instante de referencia.

El estado de Safety Car, VSC, banderas y sesión se reconstruye mediante `TrackTimeline`. Las transiciones pendientes se marcan como desconocidas; una limpieza sectorizada no borra amarillas de otros sectores.

`decision_timestamp` estima el cierre de la vuelta con `lap_date_start + lap_duration`. `accion_observada_proxima_vuelta` etiqueta la acción confirmada de la vuelta siguiente: `CONTINUAR`, `BOX_SOFT`, `BOX_MEDIUM`, `BOX_HARD`, `BOX_INTERMEDIATE` o `BOX_WET`. Las alineaciones pit–stint ambiguas, fuentes ausentes y horizontes no observables quedan nulos con un motivo.

## Calidad y límites

El contrato ejecutable está en `src/quality.py` y se usa tanto desde Airflow como desde `verify_quality_criteria.py`. Comprueba clave, volumen, columnas útiles, tipos declarados, nulos, joins futuros, estados incompatibles y coherencia de etiquetas.

La etiqueta representa una decisión observada y no demuestra optimalidad. `tyre_age` es edad en vueltas, no desgaste físico. Las variables retrospectivas y los resultados futuros se conservan para auditoría, pero no forman parte de `src/decisions.py::FEATURES`.
