import ast, json, pathlib, sys

ROOT = pathlib.Path("app/routers")
CANDIDATES = list(ROOT.glob("*.py"))
TARGET_SUB = ("coupon","validate")  # ambos deben estar en el path de la ruta

SNIP_MARK = "# WEEKDAY_TO_AT_HANDLER_TOP_START"
SNIP = [
"    " + SNIP_MARK + "\n",
"    try:\n",
"        _payload=None\n",
"        for _n,_v in list(locals().items()):\n",
"            if isinstance(_v, dict) and ('weekday' in _v or 'at' in _v): _payload=_v; break\n",
"            try:\n",
"                if getattr(_v, 'weekday', None) is not None or getattr(_v, 'at', None) is not None:\n",
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
"    # WEEKDAY_TO_AT_HANDLER_TOP_END\n",
]

def get_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None

def methods_from_keywords(call: ast.Call):
    for kw in call.keywords or []:
        if kw.arg == "methods":
            if isinstance(kw.value, ast.List):
                vals = []
                for el in kw.value.elts:
                    if isinstance(el, ast.Constant) and isinstance(el.value, str):
                        vals.append(el.value.upper())
                return vals
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return [kw.value.value.upper()]
    # decorator .post implies POST
    if isinstance(call.func, ast.Attribute) and call.func.attr.lower() == "post":
        return ["POST"]
    return None

def path_from_call(call: ast.Call):
    # decorator: first arg
    if call.args:
        p = call.args[0]
        if isinstance(p, ast.Constant) and isinstance(p.value, str):
            return p.value
    for kw in call.keywords or []:
        if kw.arg in ("path","url"):
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    return None

def find_endpoints_in_file(p: pathlib.Path):
    src = p.read_text(encoding="utf-8")
    tree = ast.parse(src)
    endpoints = []
    # decorators
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr.lower() in ("post","route","api_route"):
                    path = path_from_call(dec)
                    methods = methods_from_keywords(dec) or []
                    endpoints.append({"file": str(p), "func": node.name, "lineno": node.lineno, "path": path, "methods": methods, "node": node})
                    break
    # add_api_route
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_api_route":
            path = path_from_call(node)
            methods = methods_from_keywords(node) or []
            # endpoint function
            endpoint_name = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Name):
                endpoint_name = node.args[1].id
            for kw in node.keywords or []:
                if kw.arg == "endpoint" and isinstance(kw.value, ast.Name):
                    endpoint_name = kw.value.id
            endpoints.append({"file": str(p), "func": endpoint_name, "lineno": None, "path": path, "methods": methods, "node": None})
    return src, tree, endpoints

def choose_target():
    # scan all
    candidates = []
    file_cache = {}
    for p in CANDIDATES:
        src, tree, eps = find_endpoints_in_file(p)
        file_cache[str(p)] = (src, tree, eps)
        for e in eps:
            path = (e["path"] or "")
            path_l = path.lower()
            if all(k in path_l for k in TARGET_SUB) and ("POST" in (e["methods"] or ["POST"])):  # default post ok
                candidates.append(e)
    if not candidates:
        return None, None, None, None, None
    # prefer one with func bound
    e = None
    for c in candidates:
        if c["func"]:
            e = c; break
    if e is None:
        e = candidates[0]
    src, tree, eps = file_cache[e["file"]]
    # if decorator case: we have node
    fn_node = None
    if e["node"] is not None:
        fn_node = e["node"]
    else:
        # need to resolve by function name
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name == e["func"]:
                fn_node = n; break
    return e["file"], e["func"], e["path"], src, fn_node

def insert_snippet(src: str, fn_node: ast.FunctionDef):
    lines = src.splitlines(keepends=True)
    # compute insertion line: after docstring if present, otherwise at first stmt
    body = fn_node.body
    if not body:
        insert_line = fn_node.lineno  # after def line
        indent = 4
    else:
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            # docstring present; insert after it
            if len(body) >= 2:
                insert_line = body[1].lineno - 1
            else:
                insert_line = first.lineno  # best effort
        else:
            insert_line = first.lineno - 1
        # indentation based on that line
        raw = lines[insert_line]
        indent = len(raw) - len(raw.lstrip(" "))
    pad = " " * indent
    snip = [pad + l if l.strip() else l for l in SNIP]
    lines[insert_line:insert_line] = snip
    return "".join(lines)

def main():
    fpath, fname, path, src, fn_node = choose_target()
    if not fpath or not fn_node:
        print("NO_TARGET")
        return 2
    if SNIP_MARK in src:
        print("ALREADY", fpath, fname, path)
        return 0
    new_src = insert_snippet(src, fn_node)
    pathlib.Path(fpath).write_text(new_src, encoding="utf-8")
    print("PATCHED", fpath, fname, path)
    return 0

if __name__ == "__main__":
    sys.exit(main())
