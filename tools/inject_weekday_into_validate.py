import ast, pathlib, sys

P = pathlib.Path("app/routers/pos_coupons.py")
MARK = "# WEEKDAY_AT_SNIPPET_START"

SNIP = [
"    " + MARK + "\n",
"    try:\n",
"        # Si llega 'weekday' y no llega 'at', fijar 'at' al proximo dia solicitado (12:00 UTC)\n",
"        _payload=None\n",
"        for _n,_v in list(locals().items()):\n",
"            if isinstance(_v, dict) and ('weekday' in _v or 'at' in _v or 'code' in _v): _payload=_v; break\n",
"            try:\n",
"                if any(getattr(_v, a, None) is not None for a in ('weekday','at','code')):\n",
"                    _payload=_v; break\n",
"            except Exception:\n",
"                pass\n",
"        def _pget(k):\n",
"            try:\n",
"                if isinstance(_payload, dict): return _payload.get(k)\n",
"                return getattr(_payload, k, None)\n",
"            except Exception: return None\n",
"        def _pset(k,v):\n",
"            try:\n",
"                if isinstance(_payload, dict): _payload[k]=v\n",
"                else: setattr(_payload, k, v)\n",
"            except Exception: pass\n",
"        _wd=_pget('weekday'); _at=_pget('at')\n",
"        if _wd and not _at:\n",
"            import datetime as _dt\n",
"            def _wd_idx(w):\n",
"                s=str(w).strip().lower(); m={'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}\n",
"                return m.get(s[:3], m.get(s))\n",
"            i=_wd_idx(_wd)\n",
"            if i is not None:\n",
"                base=_dt.datetime.utcnow().replace(hour=12,minute=0,second=0,microsecond=0)\n",
"                shift=(i-base.weekday())%7\n",
"                at=(base+_dt.timedelta(days=shift)).isoformat()\n",
"                _pset('at', at)\n",
"    except Exception:\n",
"        pass\n",
"    # WEEKDAY_AT_SNIPPET_END\n",
]

def find_validate_func(src: str):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    if dec.func.attr.lower() in ("post","route","api_route"):
                        # path puede estar en args[0] o en kw 'path'/'url'
                        path_val = None
                        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value,str):
                            path_val = dec.args[0].value
                        for kw in dec.keywords or []:
                            if kw.arg in ("path","url"):
                                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value,str):
                                    path_val = kw.value.value
                        if path_val == "/validate":  # con prefix="/pos/coupon"
                            return node
    return None

def insert_at_func_top(src: str, fn: ast.FunctionDef) -> str:
    lines = src.splitlines(keepends=True)
    # Insert despues de docstring si existe; si no, antes de la primera sentencia
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        insert_line = (body[1].lineno - 1) if len(body) >= 2 else (body[0].lineno)
    else:
        insert_line = body[0].lineno - 1 if body else fn.lineno
    # calcular indentacion
    raw = lines[insert_line]
    indent = len(raw) - len(raw.lstrip(" "))
    pad = " " * indent
    snip = [pad + l if l.strip() else l for l in SNIP]
    lines[insert_line:insert_line] = snip
    return "".join(lines)

def main():
    src = P.read_text(encoding="utf-8")
    if MARK in src:
        print("ALREADY")
        return 0
    fn = find_validate_func(src)
    if not fn:
        print("NO_VALIDATE")
        return 2
    new_src = insert_at_func_top(src, fn)
    P.write_text(new_src, encoding="utf-8")
    print("PATCHED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
