"""Small Astro example DAG retained for local template compatibility."""
from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="example_astronauts",
    start_date=datetime(2025, 4, 22),
    schedule="@daily",
    catchup=False,
    default_args={"owner": "Astro", "retries": 3},
    tags=["example"],
)
def example_astronauts():
    @task
    def get_astronauts():
        return [{"craft": "ISS", "name": "Example astronaut"}]

    @task
    def print_astronaut(person):
        print(f"{person['name']} currently in space flying on {person['craft']}!")

    print_astronaut.expand(person=get_astronauts())


example_astronauts()
