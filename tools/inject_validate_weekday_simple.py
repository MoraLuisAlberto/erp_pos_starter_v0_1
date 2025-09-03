import ast
import pathlib
import sys

P = pathlib.Path("app/routers/pos_coupons.py")
MARK = "# WEEKDAY_AT_SNIPPET_SIMPLE_START"

SNIP = [
    "try:\n",
    "    # Si llega payload.weekday y no llega payload.at, fijar at al proximo dia solicitado (12:00 UTC)\n",
    "    if 'payload' in locals():\n",
    "        _wd = getattr(payload, 'weekday', None)\n",
    "        _at = getattr(payload, 'at', None)\n",
    "        if _wd and not _at:\n",
    "            import datetime as _dt\n",
    "            def _wd_idx(w):\n",
    "                s=str(w).strip().lower(); m={'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}\n",
    "                return m.get(s[:3], m.get(s))\n",
    "            i=_wd_idx(_wd)\n",
    "            if i is not None:\n",
    "                base=_dt.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)\n",
    "                shift=(i - base.weekday()) % 7\n",
    "                at=(base + _dt.timedelta(days=shift)).isoformat()\n",
    "                try: setattr(payload, 'at', at)\n",
    "                except Exception: pass\n",
    "except Exception:\n",
    "    pass\n",
    "# WEEKDAY_AT_SNIPPET_SIMPLE_END\n",
]


def find_validate_func(src: str):
    t = ast.parse(src)
    for node in ast.walk(t):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    if dec.func.attr.lower() in ("post", "route", "api_route"):
                        # path en args[0] o kw 'path'/'url'
                        path_val = None
                        if (
                            dec.args
                            and isinstance(dec.args[0], ast.Constant)
                            and isinstance(dec.args[0].value, str)
                        ):
                            path_val = dec.args[0].value
                        for kw in dec.keywords or []:
                            if kw.arg in ("path", "url"):
                                if isinstance(kw.value, ast.Constant) and isinstance(
                                    kw.value.value, str
                                ):
                                    path_val = kw.value.value
                        if path_val == "/validate":
                            return node
    return None


def insert_snippet(src: str, fn: ast.FunctionDef) -> str:
    lines = src.splitlines(keepends=True)
    # Punto de insercion: despues de docstring si existe, si no, en la primera sentencia
    body = fn.body
    if not body:
        insert_line = fn.lineno  # despues de def
        # para indent, usamos 4 espacios por defecto
        indent_str = " " * 4
    else:
        first = body[0]
        # si hay docstring como primer expr, insertar despues de el
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            if len(body) >= 2:
                insert_line = body[1].lineno - 1
                ref = body[1]
            else:
                insert_line = first.lineno
                ref = first
        else:
            insert_line = first.lineno - 1
            ref = first
        # deducir indentacion exacta de esa linea de referencia
        raw = lines[insert_line]
        lead_len = len(raw) - len(raw.lstrip())
        indent_str = raw[:lead_len]
    # Si ya existe el marcador, no duplicar
    if MARK in src:
        return src
    # Construir snippet con indent exacto
    snip = [indent_str + s if s.strip() else s for s in SNIP]
    lines[insert_line:insert_line] = snip
    return "".join(lines)


def main():
    src = P.read_text(encoding="utf-8")
    fn = find_validate_func(src)
    if not fn:
        print("NO_VALIDATE_FUNC")
        return 2
    new_src = insert_snippet(src, fn)
    P.write_text(new_src, encoding="utf-8")
    print("PATCHED_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
