import ast, pathlib, sys, re

P = pathlib.Path("app/routers/pos_coupons.py")
MARK_S = "# WEEKDAY_AT_SNIPPET_SIMPLE_START"
MARK_E = "# WEEKDAY_AT_SNIPPET_SIMPLE_END"

SNIP = [
"try:\n",
"    # Normalizar weekday: strings -> indice (0..6) y generar 'at' si falta (proximo dia 12:00 UTC)\n",
"    if 'payload' in locals():\n",
"        _wd = getattr(payload, 'weekday', None)\n",
"        _at = getattr(payload, 'at', None)\n",
"        def _wd_idx(w):\n",
"            s=str(w).strip().lower()\n",
"            m={'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,\n",
"               'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}\n",
"            return m.get(s[:3], m.get(s) if isinstance(s,str) else None)\n",
"        idx = None\n",
"        if isinstance(_wd, str):\n",
"            idx = _wd_idx(_wd)\n",
"            if idx is not None:\n",
"                try: setattr(payload, 'weekday', idx)\n",
"                except Exception: pass\n",
"        elif isinstance(_wd, int):\n",
"            idx = _wd\n",
"        if idx is not None and not _at:\n",
"            import datetime as _dt\n",
"            base=_dt.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)\n",
"            shift=(idx - base.weekday()) % 7\n",
"            at=(base + _dt.timedelta(days=shift)).isoformat()\n",
"            try: setattr(payload, 'at', at)\n",
"            except Exception: pass\n",
"except Exception:\n",
"    pass\n",
]

def find_validate_func(src: str):
    t = ast.parse(src)
    for node in ast.walk(t):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr.lower() in ('post','route','api_route'):
                    path_val = None
                    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                        path_val = dec.args[0].value
                    for kw in dec.keywords or []:
                        if kw.arg in ('path','url'):
                            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                path_val = kw.value.value
                    if path_val == "/validate":
                        return node
    return None

def insert_or_replace(src: str, fn: ast.FunctionDef) -> str:
    # Si ya hay bloque entre MARK_S..MARK_E, reemplazarlo (para evitar duplicados/errores previos)
    if MARK_S in src and MARK_E in src:
        pat = re.compile(r"^([ \\t]*)" + re.escape(MARK_S) + r"[\\s\\S]*?" + re.escape(MARK_E) + r"\\s*$", re.M)
        # Mantener la misma indentacion capturada
        def repl(m):
            indent = m.group(1)
            snip = [indent + MARK_S + "\\n"] + [indent + s for s in SNIP] + [indent + MARK_E + "\\n"]
            return "".join(snip)
        return pat.sub(repl, src, count=1)

    # Insertar despues del docstring o antes de la primera sentencia
    lines = src.splitlines(keepends=True)
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        # hay docstring
        insert_line = body[1].lineno - 1 if len(body) >= 2 else body[0].lineno
        ref = body[1] if len(body) >= 2 else body[0]
    else:
        insert_line = body[0].lineno - 1 if body else fn.lineno
        ref = body[0] if body else fn
    raw = lines[insert_line]
    lead = len(raw) - len(raw.lstrip())
    indent = raw[:lead]
    snip = [indent + MARK_S + "\\n"] + [indent + s for s in SNIP] + [indent + MARK_E + "\\n"]
    lines[insert_line:insert_line] = snip
    return "".join(lines)

def main():
    src = P.read_text(encoding="utf-8")
    t = ast.parse(src)
    fn = find_validate_func(src)
    if not fn:
        print("NO_VALIDATE_FUNC")
        return 2
    new_src = insert_or_replace(src, fn)
    P.write_text(new_src, encoding="utf-8")
    print("PATCHED_OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
