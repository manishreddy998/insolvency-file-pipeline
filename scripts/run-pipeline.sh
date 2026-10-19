#!/bin/sh
# Runs inside the pipeline container: the whole Dagster job, then the score file.
set -e
mkdir -p "$DAGSTER_HOME"
dagster job execute -m orchestration.definitions -j file_to_finish
