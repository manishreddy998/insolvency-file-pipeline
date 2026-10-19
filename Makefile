.PHONY: up down pipeline small test gate dbt clean

up:          ## everything: database, local model, pipeline, API, dashboard, Dagster UI, MLflow UI
	docker compose up --build

down:
	docker compose down

pipeline:    ## rerun the full pipeline (300 packets)
	docker compose run --rm pipeline

small:       ## 24 packets, quick check
	docker compose run --rm pipeline python -m filepipe.pipeline --small

test:
	docker compose run --rm --no-deps pipeline pytest -q -p no:cacheprovider

gate:        ## extraction gate with the negative control, same as CI
	docker compose run --rm --no-deps pipeline sh -c "python -m filepipe.gate --no-mlflow && python -m filepipe.gate --no-mlflow --candidate layout-v2-fastocr --expect-block"

dbt:
	docker compose run --rm pipeline sh -c "python -m filepipe.load && dbt build --project-dir dbt --target-path /tmp/dbt-target --log-path /tmp/dbt-logs"

clean:
	docker compose down -v
