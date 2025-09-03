import ast
import pathlib
import sys

P = pathlib.Path("app/routers/pos_coupons.py")
MARK_S = "# NORMALIZE_WEEKDAY_AT_START"
MARK_E = "# NORMALIZE_WEEKDAY_AT_END"

SNIP_BODY = [
    "try:\n",
    "    # Normalizar weekday (str -> 0..6) y generar 'at' si falta (proximo dia 12:00 UTC)\n",
    "    _wd = getattr({PAY}, 'weekday', None)\n",
    "    _at = getattr({PAY}, 'at', None)\n",
    "    def _wd_idx(w):\n",
    "        s = str(w).strip().lower()\n",
    "        m = {\n",
    "            'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,\n",
    "            'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6\n",
    "        }\n",
    "        return m.get(s[:3], m.get(s) if isinstance(s,str) else None)\n",
    "    idx = None\n",
    "    if isinstance(_wd, str):\n",
    "        idx = _wd_idx(_wd)\n",
    "        if idx is not None:\n",
    "            try: setattr({PAY}, 'weekday', idx)\n",
    "            except Exception: pass\n",
    "    elif isinstance(_wd, int):\n",
    "        idx = _wd\n",
    "    if idx is not None and not _at:\n",
    "        import datetime as _dt\n",
    "        base = _dt.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)\n",
    "        shift = (idx - base.weekday()) % 7\n",
    "        at = (base + _dt.timedelta(days=shift)).isoformat()\n",
    "        try: setattr({PAY}, 'at', at)\n",
    "        except Exception: pass\n",
    "except Exception:\n",
    "    pass\n",
]


def load_text():
    s = P.read_text(encoding="utf-8")
    # tabs -> 4 espacios para estabilizar indentaciones
    if "\\t" in s:
        s = s.replace("\\t", "    ")
        P.write_text(s, encoding="utf-8")
    return s


def find_validate_func(tree: ast.AST):
    for node in ast.walk(tree):
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


def arg_payload_name(fn: ast.FunctionDef):
    # devuelve el primer arg no-self comunmente usado para el body (payload)
    for a in fn.args.args:
        if a.arg not in ("self", "request", "req", "r"):
            return a.arg
    # fallback
    return fn.args.args[0].arg if fn.args.args else "payload"


def insert_snippet(src: str, fn: ast.FunctionDef, payload_name: str) -> str:
    if MARK_S in src and MARK_E in src:
        return src  # ya insertado
    lines = src.splitlines(keepends=True)
    body = fn.body
    # punto de insercion: despues de docstring si existe, si no, en la primera sentencia
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        insert_line = (body[1].lineno - 1) if len(body) >= 2 else (body[0].lineno)
        ref_line = lines[insert_line]
    else:
        insert_line = (body[0].lineno - 1) if body else fn.lineno
        ref_line = lines[insert_line]
    # indent de la linea de referencia
    lead = len(ref_line) - len(ref_line.lstrip())
    indent = ref_line[:lead]
    # construir snippet con indent
    snip = [indent + MARK_S + "\\n"]
    for s in SNIP_BODY:
        snip.append(indent + s.replace("{PAY}", payload_name))
    snip.append(indent + MARK_E + "\\n")
    lines[insert_line:insert_line] = snip
    return "".join(lines)


def main():
    src = load_text()
    tree = ast.parse(src)
    fn = find_validate_func(tree)
    if not fn:
        print("NO_VALIDATE_FUNC")
        return 2
    payload = arg_payload_name(fn)
    new_src = insert_snippet(src, fn, payload)
    P.write_text(new_src, encoding="utf-8")
    print("PATCHED_OK", payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
