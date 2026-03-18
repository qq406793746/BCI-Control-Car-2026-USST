# Session Log 2026-03-18: GUI EXE and Online Run

## Goal

Fix the local environment and startup errors for `code/online/main_app.py`,
get the GUI running, package it as a Windows executable, and verify the
online pipeline with `sender.py`.

## Changes

- added `code/online/torch_bootstrap.py`
  - provides a best-effort Windows DLL bootstrap for PyTorch
  - fixes `ModuleNotFoundError: torch_bootstrap` in `main_app.py`
- added `code/online/app_paths.py`
  - centralizes resource path resolution for source mode and frozen EXE mode
- updated `code/online/receiver.py`
  - loads `onlinev50pro/` artifacts and `cue_timeline/` via `resource_path(...)`
- added `code/online/main_app.spec`
  - PyInstaller spec for packaging the GUI
  - bundles `onlinev50pro/`, `cue_timeline/`, and `mne` `.pyi` stub files
- added `code/online/build_main_app_exe.ps1`
  - one-step build script for the GUI executable
- added `docs/build-gui-exe.md`
  - short packaging instructions
- updated `requirements.txt`
  - changed `scikit-learn` to `1.7.2` to match the serialized model artifacts
- updated `.gitignore`
  - excludes `code/online/build/` and `code/online/dist/`

## Validation

- confirmed the VS Code interpreter points to:
  - `C:\Users\123\AppData\Local\Programs\Python\Python39\python.exe`
- verified imports:
  - `numpy`, `scipy`, `matplotlib`, `joblib`, `sklearn`, `mne`, `torch`,
    `pylsl`, `pyxdf`, `tkinter`
- verified source startup:
  - `main_app.py` imports successfully
  - `BCIProcessor(25)` loads the model artifacts successfully
  - Tk GUI initializes successfully
- verified data path:
  - `sender.py` loads `Data/BCICIV_2a_gdf/A05E.gdf`
- verified socket path:
  - `sender.py` listens on `0.0.0.0:65432`
- installed PyInstaller from downloaded wheel files because local `pip`
  resolver/TLS behavior was broken for direct online installs
- built EXE successfully:
  - `code/online/dist/BCI-Control-Car/BCI-Control-Car.exe`
- fixed one EXE startup failure:
  - initial package missed `mne/__init__.pyi`
  - updated the spec to collect `mne` stub files
- verified packaged EXE startup:
  - window title `脑控小车演示系统 v6.1`
- verified online run readiness:
  - GUI running
  - `sender.py` running
  - local port `65432` listening

## Notes

- current runtime still shows a `scikit-learn` version mismatch warning until
  the local environment is upgraded from `1.5.2` to `1.7.2`
- build artifacts are intentionally excluded from git
