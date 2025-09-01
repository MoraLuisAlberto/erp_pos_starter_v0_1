from __future__ import annotations
import os, tempfile, io, json

__all__ = ["atomic_write_text", "write_json_atomic", "append_jsonl_atomic"]

def atomic_write_text(path: str, text: str, encoding: str = "utf-8") -> None:
    """
    Escritura atómica por reemplazo: escribe en un archivo temporal y luego hace os.replace().
    """
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with io.open(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

def write_json_atomic(path: str, obj, ensure_ascii: bool = False, separators=(",", ":")) -> None:
    """
    Serializa a JSON y escribe de forma atómica.
    """
    s = json.dumps(obj, ensure_ascii=ensure_ascii, separators=separators)
    atomic_write_text(path, s)

def append_jsonl_atomic(path: str, obj, ensure_ascii: bool = False) -> None:
    """
    Anexa una línea JSON (JSONL). Para append usamos flush+fsync para minimizar riesgo
    de cortes, pero no se hace replace del archivo completo para mantener O(1).
    """
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=ensure_ascii)
    # Nota: en Windows fsync funciona sobre el handle; esto es suficiente para nuestros tests.
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
