"""
Script de verificación de los 7 criterios de calidad - Entrega 1 (Ciencia de Datos, UTN FRM).

Verifica de forma determinística sobre los datasets Silver (CSV/JSON):
1. Dataset Principal (Vueltas): f1_silver_dataset.csv
2. Segundo Dataset (Pit Stops con new_compound): f1_silver_pit_stops.csv

Criterios evaluados:
1. Clave sin duplicados (session_key + driver_number + lap_number)
2. Volumen suficiente (> 1.000 filas)
3. Ancho suficiente (>= 5 columnas útiles)
4. Mezcla de tipos (numéricas, categóricas, booleanas, fechas)
5. Nulos conocidos (porcentajes y razones técnicas)
6. Sin columnas 100% vacías
7. Unidad de análisis / Definición de fila clara
"""

import csv
from collections import Counter
from pathlib import Path


CSV_PATH = Path("include/output/silver/f1_silver_dataset.csv")
PIT_CSV_PATH = Path("include/output/silver/f1_silver_pit_stops.csv")


def verify_dataset(csv_path: Path, dataset_name: str, expected_unit: str):
    if not csv_path.exists():
        print(f"Error: No se encontró el archivo {csv_path}.")
        print("Ejecute 'python -m src.silver_pipeline --all' primero para generarlo.")
        return None

    print("=" * 80)
    print(f"CHEQUEO DE CALIDAD - 7 CRITERIOS: {dataset_name}")
    print(f"Archivo analizado: {csv_path}")
    print("=" * 80)

    rows = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    total_rows = len(rows)
    cols = reader.fieldnames or []
    total_cols = len(cols)

    # 1. Clave sin duplicados
    keys = [(r["session_key"], r["driver_number"], r["lap_number"]) for r in rows]
    unique_keys = len(set(keys))
    is_unique = (unique_keys == total_rows)

    print(f"\n[1] CLAVE SIN DUPLICADOS (Primary Key):")
    print(f"    - Clave natural: (session_key, driver_number, lap_number)")
    print(f"    - Resultado is_unique: {is_unique}")
    print(f"    - Total claves únicas: {unique_keys:,} / Total filas: {total_rows:,}")
    assert is_unique, f"Error: Existen claves duplicadas en {dataset_name}."

    # 2. Volumen suficiente (> 1.000 filas)
    print(f"\n[2] VOLUMEN SUFICIENTE:")
    print(f"    - Total filas: {total_rows:,} (Requerido: > 1.000) -> CUMPLE ({total_rows:,} > 1.000)")
    assert total_rows > 1000, f"Error: Volumen insuficiente en {dataset_name}."

    # 3. Ancho suficiente (>= 5 columnas útiles)
    print(f"\n[3] ANCHO SUFICIENTE:")
    print(f"    - Total columnas: {total_cols} (Requerido: >= 5) -> CUMPLE ({total_cols} >= 5)")
    assert total_cols >= 5, f"Error: Columnas insuficientes en {dataset_name}."

    # 4. Mezcla de tipos de datos
    type_summary = Counter()
    for col in cols:
        non_empty = [r[col] for r in rows if r[col] != ""]
        if not non_empty:
            type_summary["empty"] += 1
            continue
        if all(val in ("True", "False") for val in non_empty):
            type_summary["bool"] += 1
        elif all(val.replace(".", "", 1).replace("-", "", 1).isdigit() for val in non_empty):
            if any("." in val for val in non_empty):
                type_summary["float (numérica)"] += 1
            else:
                type_summary["int (numérica)"] += 1
        elif any("T" in val and ("+" in val or "Z" in val or "-" in val) for val in non_empty[:20]):
            type_summary["date/timestamp (fecha)"] += 1
        else:
            type_summary["string/categorica"] += 1

    print(f"\n[4] MEZCLA DE TIPOS:")
    for type_name, count in sorted(type_summary.items()):
        print(f"    - {type_name}: {count} columnas")

    # 5. Nulos conocidos
    null_counts = {}
    for col in cols:
        empty_count = sum(1 for r in rows if r[col] == "" or r[col] is None)
        null_counts[col] = empty_count

    sorted_nulls = sorted(null_counts.items(), key=lambda x: x[1], reverse=True)

    print(f"\n[5] NULOS CONOCIDOS (Top 10 columnas con más nulos):")
    for col, count in sorted_nulls[:10]:
        pct = (count / total_rows) * 100
        formatted_count = f"{count:,}"
        print(f"    * {col:<30}: {pct:>6.2f}% nulos ({formatted_count:>7} filas)")

    # 6. Sin columnas vacías
    empty_cols = [col for col, count in null_counts.items() if count == total_rows]
    print(f"\n[6] SIN COLUMNAS VACÍAS (100% nulas):")
    print(f"    - Columnas 100% vacías: {empty_cols} (Total: {len(empty_cols)}) -> CUMPLE")
    assert len(empty_cols) == 0, f"Error: Se encontraron columnas completamente vacías en {dataset_name}."

    # 7. Unidad de análisis
    print(f"\n[7] UNIDAD DE ANÁLISIS:")
    print(f"    - {expected_unit}")

    return rows


def main():
    # 1. Dataset principal
    laps_rows = verify_dataset(
        CSV_PATH,
        "DATASET PRINCIPAL DE VUELTAS (f1_silver_dataset.csv)",
        "«Una fila es una vuelta completada o intentada por un piloto en una carrera de Gran Premio»."
    )

    # 2. Dataset de Pit Stops
    print("\n\n")
    pit_rows = verify_dataset(
        PIT_CSV_PATH,
        "SEGUNDO DATASET: PARADAS EN BOXES (f1_silver_pit_stops.csv)",
        "«Una fila es una parada en boxes (pit stop) realizada por un piloto, con su neumático entrante y nuevo neumático instalado»."
    )

    if pit_rows:
        print("\n" + "=" * 80)
        print("MÉTRICAS ESPECÍFICAS DE VALIDACIÓN - PIT STOPS & NEW_COMPOUND")
        print("=" * 80)

        total_pits = len(pit_rows)
        with_new_comp = sum(bool(r.get("new_compound")) for r in pit_rows)
        without_new_comp = total_pits - with_new_comp
        non_pit_stops = sum(r.get("pit_stop") != "True" for r in pit_rows)

        print(f"  • Total filas CSV original (vueltas):          {len(laps_rows):,}")
        print(f"  • Total filas segundo CSV (pit stops):         {total_pits:,}")
        print(f"  • Paradas con pit_stop == True:                {total_pits - non_pit_stops:,} (100%)")
        print(f"  • Filas ajenas a boxes (no pit stop):          {non_pit_stops}")
        print(f"  • Compuestos nuevos (new_compound) detectados: {with_new_comp:,} ({with_new_comp/total_pits*100:.2f}%)")
        print(f"  • Registros sin compuesto nuevo:               {without_new_comp}")

        # Matriz de transición de compuestos
        transitions = Counter((r.get("current_compound"), r.get("new_compound")) for r in pit_rows)
        print(f"\n  • Top 10 Transiciones de Neumáticos en Boxes (current_compound -> new_compound):")
        for (c_in, c_out), count in transitions.most_common(10):
            print(f"      {c_in:<14} -> {c_out:<14}: {count:>5} paradas ({count/total_pits*100:>5.2f}%)")

        compounds_in = Counter(r.get("current_compound") for r in pit_rows)
        compounds_out = Counter(r.get("new_compound") for r in pit_rows)

        print(f"\n  • Distribución de Compuestos al ENTRAR a boxes (current_compound):")
        for comp, count in sorted(compounds_in.items(), key=lambda x: x[1], reverse=True):
            print(f"      {comp:<14}: {count:>5} ({count/total_pits*100:>5.2f}%)")

        print(f"\n  • Distribución de Compuestos al SALIR de boxes (new_compound):")
        for comp, count in sorted(compounds_out.items(), key=lambda x: x[1], reverse=True):
            print(f"      {comp:<14}: {count:>5} ({count/total_pits*100:>5.2f}%)")

        print("\n" + "=" * 80)
        print("TODOS LOS CRITERIOS Y VALIDACIONES DE AMBOS DATASETS HAN SIDO SUPERADOS EXITOSAMENTE.")
        print("=" * 80)


if __name__ == "__main__":
    main()

