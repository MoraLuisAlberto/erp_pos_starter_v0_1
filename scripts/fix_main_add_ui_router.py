import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
MAIN = os.path.join(ROOT, "app", "main.py")

IMP = "from app.routers import ui as _ui_router"
INC = "app.include_router(_ui_router.router)"


def run():
    with open(MAIN, encoding="utf-8") as f:
        src = f.read()
    changed = False
    if IMP not in src:
        src = IMP + "\n" + src
        changed = True
    if INC not in src:
        # insertar tras la creación de FastAPI o al final si no se encuentra
        m = re.search(r"app\s*=\s*FastAPI\([^)]*\)", src)
        if m:
            idx = m.end()
            src = src[:idx] + "\n" + INC + "\n" + src[idx:]
        else:
            src = src + "\n" + INC + "\n"
        changed = True
    with open(MAIN, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    print("OK: main.py actualizado" if changed else "OK: main.py ya tenía UI router")


if __name__ == "__main__":
    run()
