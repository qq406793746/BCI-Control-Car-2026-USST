import os
import site
from pathlib import Path


def _candidate_dirs():
    seen = set()
    for base in site.getsitepackages():
        torch_lib = Path(base) / "torch" / "lib"
        if torch_lib.is_dir():
            resolved = str(torch_lib.resolve())
            if resolved not in seen:
                seen.add(resolved)
                yield torch_lib


def prepare_torch_dlls():
    """Best-effort helper for Windows PyTorch DLL lookup."""
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return

    for dll_dir in _candidate_dirs():
        try:
            os.add_dll_directory(str(dll_dir))
        except OSError:
            continue
