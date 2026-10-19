"""Paths and settings shared by every step. Everything can be moved with environment variables."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("FILEPIPE_ROOT", Path(__file__).resolve().parents[2]))
DATA = Path(os.environ.get("FILEPIPE_DATA", ROOT / "data"))
RESULTS = Path(os.environ.get("FILEPIPE_RESULTS", ROOT / "results"))
CONFIGS = ROOT / "configs"

PACKETS = DATA / "packets"
RAW = DATA / "raw"
WORK = DATA / "work"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "")


def llm_url() -> str:
    return os.environ.get("LLM_URL", "")


def llm_model() -> str:
    return os.environ.get("LLM_MODEL", "qwen2.5-1.5b-instruct")


def mlflow_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{DATA / 'mlflow.db'}")


def mlflow_experiment(name: str) -> None:
    """Point MLflow at the tracking store and keep artifacts under data/, which every container mounts."""
    import mlflow
    mlflow.set_tracking_uri(mlflow_uri())
    if mlflow.get_experiment_by_name(name) is None:
        art = DATA / "mlartifacts" / name
        art.mkdir(parents=True, exist_ok=True)
        mlflow.create_experiment(name, artifact_location=art.resolve().as_uri())
    mlflow.set_experiment(name)


def ensure_dirs() -> None:
    for p in (DATA, RESULTS, PACKETS, RAW, WORK):
        p.mkdir(parents=True, exist_ok=True)
