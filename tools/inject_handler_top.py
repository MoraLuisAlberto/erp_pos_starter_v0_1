import ast
import sys

P = r"app/routers/coupon.py"
MARK = "# WEEKDAY_TO_AT_SNIPPET_TOP_START"
SNIP = [
    "    # WEEKDAY_TO_AT_SNIPPET_TOP_START\n",
    "    try:\n",
    "        # Si llega 'weekday' y no llega 'at', calcular proximo 'at' 12:00 UTC\n",
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
    "    # WEEKDAY_TO_AT_SNIPPET_TOP_END\n",
]


def find_coupon_validate_posts(src):
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "post"
                ):
                    path_val = None
                    if (
                        dec.args
                        and isinstance(dec.args[0], ast.Constant)
                        and isinstance(dec.args[0].value, str)
                    ):
                        path_val = dec.args[0].value
                    for kw in dec.keywords or []:
                        if kw.arg in ("path", "url"):
                            v = kw.value
                            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                                path_val = v.value
                    if path_val and ("coupon" in path_val and "validate" in path_val):
                        out.append(node)
                        break
    return out


def main():
    with open(P, encoding="utf-8") as f:
        src = f.read()
    if MARK in src:
        print("ALREADY")
        return 0
    posts = find_coupon_validate_posts(src)
    if not posts:
        print("NO_MATCH")
        return 2
    lines = src.splitlines(keepends=True)
    node = posts[0]
    insert_line = node.body[0].lineno - 1  # inicio del cuerpo
    indent = len(lines[insert_line]) - len(lines[insert_line].lstrip(" "))
    pad = " " * indent
    snip = [pad + l if l.strip() else l for l in SNIP]
    lines[insert_line:insert_line] = snip
    with open(P, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("PATCHED_AT_TOP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
