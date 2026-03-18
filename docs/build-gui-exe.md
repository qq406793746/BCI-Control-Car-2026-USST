# Build GUI EXE

This project can package `code/online/main_app.py` into a Windows executable.

## Why `onedir`

Use `PyInstaller` `onedir` mode first:
- the app depends on `torch`
- it loads model artifacts from `code/online/onlinev50pro/`
- it loads cue files from `code/online/cue_timeline/`

`onedir` is more stable than `onefile` for this project.

## Build

From `code/online/`:

```powershell
py -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File .\build_main_app_exe.ps1
```

## Output

```text
code/online/dist/BCI-Control-Car/BCI-Control-Car.exe
```

## Notes

- The spec file is `code/online/main_app.spec`.
- The build script is `code/online/build_main_app_exe.ps1`.
- `receiver.py` now resolves resources correctly in both source mode and frozen mode.
