# Pendientes para la Entrega 4

Lo que sale de la Entrega 3 y hay que tener presente. El modelo elegido en la Entrega 3 es el que usa la app, según el instructivo.

## Punto de partida

- **Modelo:** regresión logística (`C=0,003`, `class_weight="balanced"`) sobre `new_compound` (SOFT, MEDIUM, HARD o LLUVIA). Notebook: [`Entrega3/Entrega3_Modelado.ipynb`](../Entrega3/Entrega3_Modelado.ipynb).
- **Rendimiento:** F1 macro 0,503 en la validación repetida y 0,651 en el test 2025. El test ya se miró, así que **cualquier mejora nueva se evalúa con datos que el modelo no haya visto** (por ejemplo, las carreras de 2025 posteriores a la descarga, o la temporada 2026).
- **Por qué no da más:** con la misma situación sacada de otras carreras se llega a 0,500, lo mismo que el modelo. Dentro de la misma carrera, los pilotos coinciden con F1 0,836. Lo que falta es **información de la carrera**, no un modelo más complejo (sección 14 del notebook).

## 1. Datos nuevos en el pipeline (la mejora con más potencial)

### 1.1 Juegos de neumáticos disponibles por piloto

Es lo que explica la confusión más típica del modelo: SOFT o HARD como segundo compuesto con unas 20 vueltas por delante (Japón 2025: Lawson y Sainz).

- **Fuente:** el endpoint `stints` de OpenF1 para las sesiones de **entrenamientos (FP1–FP3), sprint y clasificación** del mismo fin de semana. Un stint con `tyre_age_at_start = 0` es un juego nuevo.
- **Cambio en el pipeline:**
  - Hoy `discover_race_sessions` sólo descarga carreras. Hay que sumar las otras sesiones del meeting a la capa bronce, en una carpeta propia por sesión.
  - En silver, una tabla `tyre_sets` por piloto y meeting: juegos nuevos usados de cada compuesto antes de la carrera.
- **Columnas para el modelo:**
  - `new_sets_left_soft`, `new_sets_left_medium` y `new_sets_left_hard`: los juegos que tiene asignados (13 por fin de semana con el formato estándar) menos los usados antes de la parada.
  - Antes de confirmar la columna, verificar la asignación por compuesto, que varía según el fin de semana y el año.
- **Cuidado con la fuga:** sólo contar los juegos usados **antes** de la vuelta del pit, incluidos los de la carrera.

### 1.2 Nominación de Pirelli por circuito

Qué compuesto C1–C5 es el HARD, el MEDIUM y el SOFT en cada carrera. Es pública y se conoce antes del fin de semana.

- **Fuente:** los comunicados de Pirelli; OpenF1 no la publica. Es una tabla chica para cargar a mano: unas 24 carreras por 3 temporadas.
- **Dónde:** un CSV versionado en `database/` o en `include/reference/`, unido por `meeting_key`.
- **Columnas para el modelo:** `hard_c`, `medium_c` y `soft_c`, o la distancia entre compuestos (por ejemplo, si el salto de MEDIUM a SOFT es de un escalón o de dos).

### 1.3 Ya probado y descartado en la Entrega 3 (no repetir sin un dato nuevo)

- Lo que montaron los que pararon antes en la carrera: +0,034 ± 0,047. Se puede volver a probar **combinado** con los juegos disponibles.
- Vueltas desde la última lluvia y tendencia del ritmo (para Bélgica 2025): no suman.
- Circuito y equipo como columnas, safety car, VSC, gap al líder y posición: dentro del ruido.

## 2. Calidad de datos en el pipeline

- **Bélgica 2025:** OpenF1 da un stint de INTERMEDIATE de una vuelta y otro de MEDIUM desde la vuelta 2, sin parada. Hoy se corrige en el notebook (sección 1). Hay que **llevar la regla a `src/silver_pipeline.py`** para que el CSV silver salga corregido.
- **Miami 2025:** los stints y las paradas de OpenF1 no coinciden en la vuelta del cambio. Hay que decidir qué fuente manda, o marcar esas filas.
- **Otros stints sin parada a revisar:** Bélgica 2024 (4 pilotos con un stint de una vuelta en la última vuelta), Qatar 2024 (2 pilotos con un primer stint de compuesto `UNKNOWN`) y un piloto en Australia 2025.
- **`tyre_age` en la vuelta del pit:** en algunas filas muestra la edad de la goma nueva (fuga parcial detectada en la Entrega 2). El modelo usa la vuelta anterior, pero conviene corregirlo en silver.

## 3. Para la app

- **Mover `ColumnasDerivadas` y `GapALider` a un módulo** (por ejemplo, `src/modelo.py`). Si quedan definidas en el notebook, el modelo guardado con `joblib` no se puede cargar en la app.
- **Mostrar las probabilidades de cada compuesto**, no sólo la clase ganadora. El compuesto real está entre las dos primeras opciones en el 83 % de las paradas de validación.
- **Qué carga el usuario:** compuesto actual, compuestos ya usados, vuelta y vueltas programadas, clima (temperaturas, humedad, lluvia), qué lleva el pelotón y posición y gap. Evaluar si se pueden sacar las columnas con importancia negativa (`pit_stop_number`, `field_medium_prev`, `tyre_age_prev`, `used_soft`) para simplificar el formulario, midiéndolo con validación cruzada.
- **Advertencias en la interfaz:** el modelo acierta poco en las últimas 10 vueltas (23 % en el test) y no ve el paso de intermedios a gomas de seco en una pista que se seca.
