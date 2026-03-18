import os
import sys
from pathlib import Path


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> str:
    return str(app_base_dir().joinpath(*parts))


def project_root() -> str:
    return str(Path(__file__).resolve().parents[2])


def running_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
