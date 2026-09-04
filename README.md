# f1-strategy-pipeline

Pipeline de datos para analizar estrategias de neumáticos
de Fórmula 1 utilizando OpenF1, Apache Airflow y PostgreSQL.

## Tecnologías

- Python
- Apache Airflow
- PostgreSQL
- Docker
- OpenF1 API

## Arquitectura

OpenF1 API
    ↓
Airflow
    ↓
PostgreSQL
    ↓
Feature Engineering
    ↓
Modelo de decisión