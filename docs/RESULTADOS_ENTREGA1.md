# Resultados de la Entrega 1

Versión publicada: `c17cb51d8d3f88c45d3a823b`.

La reconstrucción completa se ejecutó el 9 de septiembre de 2026 sobre el Bronce local y terminó correctamente en almacenamiento temporal antes de publicarse. La ejecución procesó 70 carreras de 2023–2025 y publicó la versión identificada por el manifiesto. La ruta vigente se indica en `include/output/silver/current.json`.

## Métricas

| Métrica | Resultado |
|---|---:|
| Carreras esperadas / procesadas | 70 / 70 |
| Filas Silver | 77.373 |
| Columnas | 117 |
| Claves duplicadas | 0 |
| Columnas completamente vacías | 0 |
| Filas elegibles y etiquetadas | 64.001 |
| Anomalías documentadas | 12 |

Distribución del objetivo `accion_observada_proxima_vuelta`:

| Clase | Filas |
|---|---:|
| `CONTINUAR` | 64.756 |
| `BOX_HARD` | 891 |
| `BOX_MEDIUM` | 530 |
| `BOX_SOFT` | 278 |
| `BOX_INTERMEDIATE` | 79 |
| `BOX_WET` | 6 |

El objetivo queda nulo en 10.833 filas porque la fuente de pits/stints está ausente, no existe la vuelta siguiente, la alineación pit–stint es ambigua, falta el instante o la ventana contiene bandera roja. No se asigna `CONTINUAR` por defecto.

## Validación

La calidad usa `src/quality.py` y es la misma lógica que utiliza el DAG y `verify_quality_criteria.py`. Comprueba tipos declarados, clave completa y única, volumen, columnas útiles, mezcla de tipos, nulos, columnas vacías, joins futuros, estados SC/VSC y coherencia de la disponibilidad del objetivo.

Las pruebas ejecutadas fueron `27 passed`, incluyendo pruebas de transformación, DAG, ingesta atómica, caché corrupta, inventario incompleto, etiquetas ambiguas, reinicios, amarillas por sector y joins con offsets horarios.

## Anomalías y límites

Las 12 anomalías restantes corresponden a seis respuestas esperadas sin datos de pits y a eventos de bandera roja que quedan documentados por sesión. La reconstrucción conservadora deja transiciones de estado desconocidas fuera de las filas elegibles. El modelo futuro debe considerar que la clase `BOX_WET` tiene muy pocos ejemplos y que `CONTINUAR` domina la distribución.

El CSV describe decisiones observadas. No demuestra que la decisión haya sido óptima: un recomendador debe estimar las consecuencias de alternativas no ejecutadas, con una función de costo, horizonte, tráfico e incertidumbre documentados.

## Cómo reproducir y verificar

```bash
python -m src.silver_pipeline --all
python verify_quality_criteria.py --csv include/output/silver/releases/<release_id>/f1_silver_dataset.csv
python -m pytest tests -q
```

En el entorno Astro, la corrida completa debe estar visible en el historial de Airflow antes de la exposición. La presentación y las preguntas preparadas están en `docs/ENTREGA1_DEFENSA.md`.
