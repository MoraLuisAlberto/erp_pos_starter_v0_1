import ast, sys

P = r"app/routers/coupon.py"
MARK = "# WEEKDAY_TO_AT_SNIPPET_TOP_START"

SNIP = [
"    # WEEKDAY_TO_AT_SNIPPET_TOP_START\n",
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
"    # WEEKDAY_TO_AT_SNIPPET_TOP_END\n",
]

def find_all_posts(src):
    tree = ast.parse(src)
    funs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr=='post':
                    funs.append(node); break
    return funs

def main():
    src = open(P, 'r', encoding='utf-8').read()
    if MARK in src:
        print('ALREADY')
        return 0
    posts = find_all_posts(src)
    if not posts:
        print('NO_POSTS')
        return 2
    lines = src.splitlines(keepends=True)
    # Insert at start of each post function body
    offset = 0
    for fn in posts:
        start = fn.body[0].lineno - 1 + offset
        indent = len(lines[start]) - len(lines[start].lstrip(' '))
        pad = ' ' * indent
        snip = [pad + l if l.strip() else l for l in SNIP]
        lines[start:start] = snip
        offset += len(snip)
    open(P, 'w', encoding='utf-8').writelines(lines)
    print('PATCHED', len(posts))
    return 0

if __name__ == "__main__":
    sys.exit(main())
