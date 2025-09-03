import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
MAIN = os.path.join(ROOT, "app", "main.py")

IMP_LINE = "from app.routers import session as _session_router_auto"
INC_LINE = 'app.include_router(_session_router_auto.router, prefix="/pos")'


def already_has(lines, needle):
    return any(needle in ln for ln in lines)


def ensure_main():
    with open(MAIN, encoding="utf-8") as f:
        src = f.read()
    lines = src.splitlines()

    changed = False

    # 1) Asegura import del router
    if not already_has(lines, IMP_LINE):
        # Inserta import después del primer bloque de imports
        insert_at = 0
        for i, ln in enumerate(lines[:50]):
            if ln.strip().startswith("from ") or ln.strip().startswith("import "):
                insert_at = i + 1
        lines.insert(insert_at, IMP_LINE)
        changed = True

    # 2) Asegura include_router sobre la variable 'app'
    if not already_has(lines, INC_LINE):
        # intenta encontrar la línea donde se crea FastAPI()
        app_idx = None
        for i, ln in enumerate(lines[:200]):
            if "FastAPI(" in ln and "=" in ln and "app" in ln.split("=")[0]:
                app_idx = i
                break
        # inserta después de la creación de app, o al final si no se encontró
        target_idx = (app_idx + 1) if app_idx is not None else len(lines)
        lines.insert(target_idx, INC_LINE)
        changed = True

    if changed:
        with open(MAIN, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
        print("PATCHED main.py -> session router included")
    else:
        print("OK main.py already includes session router")


if __name__ == "__main__":
    ensure_main()
