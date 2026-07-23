"""Planes module resolution.

`use http` and `use file` name builtin capability modules — reserved words
that unlock effects. `use utils` names a file, `utils.planes`, resolved
relative to the importing file.

Both meanings share one keyword deliberately: from the caller's side, `use`
answers one question — what does this program depend on. The analyser needs
both kinds in the same dependency graph, because a package's effect surface
includes the surface of everything it imports.
"""
import os

BUILTIN_MODULES = {"http", "file"}


class ModuleError(Exception):
    def __init__(self, name, detail, fix=""):
        self.name = name
        self.detail = detail
        self.fix = fix
        msg = f"{detail}"
        if fix:
            msg += f"\n  try: {fix}"
        super().__init__(msg)


def resolve(name, from_path):
    """Locate the file for `use name`. Returns None for builtins.

    Resolution is relative to the importing file, so a package moved as a
    directory keeps working.
    """
    if name in BUILTIN_MODULES:
        return None
    base = os.path.dirname(os.path.abspath(from_path)) if from_path else os.getcwd()
    candidate = os.path.join(base, f"{name}.planes")
    if os.path.exists(candidate):
        return candidate
    raise ModuleError(
        name,
        f"no module named '{name}'",
        f"create {name}.planes next to this file, "
        f"or use one of: {', '.join(sorted(BUILTIN_MODULES))}")


def load_graph(path, _seen=None, _stack=None, _names=None):
    """Load a file and everything it uses, depth first.

    Returns a list of (path, source) in dependency order — imports before
    importers — so a consumer can process them in one pass. Cycles raise
    rather than hang.
    """
    from parser import parse, scan_names
    from lexer import Use

    _seen = {} if _seen is None else _seen
    _stack = [] if _stack is None else _stack

    key = os.path.abspath(path)
    if key in _seen:
        return []
    if key in _stack:
        cycle = " -> ".join(os.path.basename(p) for p in _stack + [key])
        raise ModuleError(os.path.basename(path),
                          f"module cycle: {cycle}",
                          "break the cycle by moving shared code to a third file")

    src = open(path).read()
    _stack.append(key)
    ordered = []
    for mod in uses_in(src):
        target = resolve(mod, path)
        if target is not None:
            ordered.extend(load_graph(target, _seen, _stack))
    _stack.pop()

    _seen[key] = True
    ordered.append((path, src))
    return ordered


def uses_in(src):
    """Module names this source uses, read from tokens.

    Deliberately not a full parse: the file may call multi-word functions
    from a module we have not loaded yet, which a parse would reject. The
    dependency graph has to be discoverable before the parser knows enough
    to read the file.
    """
    from lexer import tokenize
    toks = tokenize(src)
    out = []
    for i, t in enumerate(toks):
        if t.kind == "USE" and i + 1 < len(toks) and toks[i + 1].kind == "NAME":
            out.append(toks[i + 1].value)
    return out


def names_in_graph(graph):
    """Every callable name in a loaded graph, after renames.

    Needed before re-parsing: a multi-word call like `api base` is two NAME
    tokens, and only a name table can tell the parser it is one call. Both
    the original and the renamed form are included, because the defining
    file still calls its own function by the original name.
    """
    names = set()
    for _path, original, effective in effective_names(graph):
        names.add(original)
        names.add(effective)
    return names


def rename_map(graph):
    """path -> {original name: name it is known by elsewhere}."""
    out = {}
    for path, original, effective in effective_names(graph):
        if original != effective:
            out.setdefault(path, {})[original] = effective
    return out


def renames_in(src):
    """Renames declared by this file, as {module: {old: new}}.

    Read from tokens for the same reason as `uses_in`: the file may call
    multi-word functions from modules not yet loaded.
    """
    from lexer import tokenize
    toks = tokenize(src)
    out = {}
    i = 0
    while i < len(toks):
        if toks[i].kind == "USE" and toks[i + 1].kind == "NAME":
            mod = toks[i + 1].value
            j = i + 2
            pairs = {}
            while toks[j].kind == "WITH":
                j += 1
                old = []
                while toks[j].kind == "NAME":
                    old.append(toks[j].value)
                    j += 1
                if toks[j].kind != "AS":
                    break
                j += 1
                new = []
                while toks[j].kind == "NAME":
                    new.append(toks[j].value)
                    j += 1
                if old and new:
                    pairs[" ".join(old)] = " ".join(new)
            if pairs:
                out.setdefault(mod, {}).update(pairs)
            i = j
            continue
        i += 1
    return out


def effective_names(graph):
    """The name each file contributes, after the importer's renames.

    A rename is declared by the file doing the importing, so it is applied
    when working out what name a definition ends up under.
    """
    from parser import scan_names
    import os

    # module basename -> renames applied to it by anyone importing it
    applied = {}
    for _, src in graph:
        for mod, pairs in renames_in(src).items():
            applied.setdefault(mod, {}).update(pairs)

    out = []
    for path, src in graph:
        mod = os.path.basename(path).replace(".planes", "")
        pairs = applied.get(mod, {})
        for name in scan_names(src):
            out.append((path, name, pairs.get(name, name)))
    return out


def check_collisions(graph):
    """Two files defining the same function name is an error.

    Names are flat across a module graph: `api base` is called as `api base`,
    not `config.api base`, because multi-word names already read as prose and
    qualifying them would fight that. Flat names make a collision genuinely
    ambiguous, so it must be reported rather than resolved.

    Silently letting load order decide would be the worst option: the same
    program would behave differently depending on the order of its `use`
    lines, with nothing to read that explains why.

    A collision is resolved by renaming at the point of use — the consumer
    of two colliding modules usually cannot edit either one, so the fix has
    to live in their own file.
    """
    import os

    owners = {}
    for path, _original, name in effective_names(graph):
        owners.setdefault(name, []).append(path)

    clashes = {n: ps for n, ps in owners.items() if len(set(ps)) > 1}
    if not clashes:
        return

    lines = []
    for name, paths in sorted(clashes.items()):
        where = ", ".join(sorted({os.path.basename(p) for p in paths}))
        lines.append(f"'{name}' is defined in {where}")
    first = sorted(clashes)[0]
    other = sorted({os.path.basename(p) for p in clashes[first]})[0]
    other_mod = other.replace(".planes", "")
    raise ModuleError(
        first,
        "two modules define the same name:\n  " + "\n  ".join(lines),
        f"rename one at the point of use, e.g. "
        f"`use {other_mod} with {first} as my {first}`")
