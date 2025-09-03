import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
MAIN = os.path.join(ROOT, "app", "main.py")

IMPORT_LINE = "from app.routers import session as _session_router_auto"
INCLUDE_LINE = 'app.include_router(_session_router_auto.router, prefix="/pos")'


def find_index(lines, predicate, max_scan=None):
    rng = range(len(lines)) if max_scan is None else range(min(max_scan, len(lines)))
    for i in rng:
        if predicate(lines[i]):
            return i
    return None


def run():
    with open(MAIN, encoding="utf-8") as f:
        src = f.read()
    lines = src.splitlines()

    changed = False

    # A) Asegura import (si no está, lo agregamos al principio)
    if IMPORT_LINE not in lines:
        lines.insert(0, IMPORT_LINE)
        changed = True

    # B) Asegura include_router (si no está, lo metemos tras la creación de app)
    inc_idx = find_index(lines, lambda ln: "include_router" in ln and "_session_router_auto" in ln)
    if inc_idx is None:
        app_idx = find_index(
            lines,
            lambda ln: "FastAPI(" in ln and "=" in ln and "app" in ln.split("=", 1)[0],
            max_scan=200,
        )
        insert_at = (app_idx + 1) if app_idx is not None else len(lines)
        lines.insert(insert_at, INCLUDE_LINE)
        changed = True
        inc_idx = find_index(
            lines, lambda ln: "include_router" in ln and "_session_router_auto" in ln
        )

    # C) Garantiza orden: import antes del include
    imp_idx = find_index(lines, lambda ln: ln.strip() == IMPORT_LINE)
    if imp_idx is None:
        # muy raro; re-insertamos al principio y recalculamos
        lines.insert(0, IMPORT_LINE)
        changed = True
        imp_idx = 0

    if imp_idx > inc_idx:
        # mover import arriba del include
        line = lines.pop(imp_idx)
        inc_idx = find_index(
            lines, lambda ln: "include_router" in ln and "_session_router_auto" in ln
        )  # recomputa
        lines.insert(inc_idx, line)
        changed = True

    if changed:
        with open(MAIN, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
        print("PATCHED: main.py (import/include ordenados)")
    else:
        print("OK: main.py ya estaba correcto")


if __name__ == "__main__":
    run()
