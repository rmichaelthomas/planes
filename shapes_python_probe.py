"""Probe: does the Shapes architecture port to a language people already write?

Not a product. Forty lines answering one question — whether the core of
shapes.py (fixed point over a call graph, effects inherited transitively by
callers) depends on Planes, or only on having an AST.

It does not depend on Planes. `compute` below inherits network reach from
`beacon` two calls down, with no annotation, using the same algorithm.

This matters because the wedge argument in the inception checkpoint assumes
Planes code exists to index, and none does. See REPORT_WEDGE.md §3.
"""
import ast

EFFECTS = {
    'open':'file', 'urlopen':'network', 'get':'network', 'post':'network',
    'print':'console', 'time':'clock', 'random':'random', 'getenv':'env',
    'system':'process', 'popen':'process',
}

def surface(src):
    tree = ast.parse(src)
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    fx = {n: set() for n in funcs}
    changed = True
    while changed:                       # same fixed point as shapes.py
        changed = False
        for name, node in funcs.items():
            found = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    f = sub.func
                    nm = getattr(f, 'id', None) or getattr(f, 'attr', None)
                    if nm in EFFECTS:
                        found.add((nm, EFFECTS[nm]))
                    elif nm in fx:
                        found |= fx[nm]
            if not found <= fx[name]:
                fx[name] |= found; changed = True
    return fx

SAMPLE = '''
def helper(n):
    return n + 1

def beacon(r):
    import urllib.request
    return urllib.request.urlopen("https://collect.example.com/?v=" + str(r))

def compute(n):
    return beacon(helper(n))
'''
for name, es in surface(SAMPLE).items():
    print(f"  {name:10} {sorted(e[1] for e in es) or ['pure']}")
