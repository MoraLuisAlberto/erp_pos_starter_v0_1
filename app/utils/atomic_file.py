import os, json, tempfile
from typing import Any, Dict

try:
    # bloqueo de archivo multiplataforma (opcional; instalar "filelock")
    from filelock import FileLock  # type: ignore
except Exception:
    FileLock = None  # fallback sin lock a nivel OS

def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

def write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    """Escribe JSON de forma atómica: temp -> os.replace()."""
    _ensure_dir(path)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

def append_jsonl_atomic(path: str, obj: Dict[str, Any]) -> None:
    """Agrega una línea JSONL; usa bloqueo si 'filelock' está disponible."""
    _ensure_dir(path)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    if FileLock:
        lock_path = path + ".lock"
        with FileLock(lock_path, timeout=5):
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
