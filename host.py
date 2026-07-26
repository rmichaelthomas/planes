"""The host: whatever actually performs an effect.

P-Q9 has been open since the first session — "what is the implementation
host". Measuring it rather than arguing it produced a smaller question than
expected.

Almost nothing in Planes is host-shaped. The parser reads a foreign target
as an opaque string. The analyser uses it as a label and never parses it.
Only the interpreter interprets it, in one place, by splitting on a dot and
calling `importlib`. Everything else — exact rationals, JSON at the
boundary, HTTP, module files — is implementation, not language.

So the host question is not "which language should Planes be written in".
It is "what does a host have to provide", and the answer is this file: five
capabilities and a way to resolve a foreign name.

Naming that surface is the useful part. A second host is then a piece of
work with a known size, rather than a rewrite, and the *language* stops
quietly accumulating assumptions about the machine underneath it.
"""
import json
import urllib.request


class HostError(Exception):
    """The host could not do what was asked. Distinct from a program error:
    this is the machine failing, not the program being wrong."""


class Host:
    """What a host must provide.

    Five capabilities, matching the closed effect vocabulary, plus foreign
    resolution. A host that implements these runs Planes; the language does
    not otherwise care what it is written in.

    The vocabulary is what makes this small. Because effects were closed
    early — `ask`, `read`, `write`, `show`, `clock`, `random`, `env` — the
    host surface could not sprawl. That was decided for the analyser, and it pays
    out here.
    """

    name = "abstract"

    # ---- effects

    def ask(self, url):
        """A request expecting a response. Returns the body as text."""
        raise NotImplementedError

    def read(self, path):
        """Read a file. Returns its contents as text."""
        raise NotImplementedError

    def write(self, path, text):
        """Write a file."""
        raise NotImplementedError

    def show(self, text):
        """Emit a line to wherever output goes."""
        raise NotImplementedError

    def clock(self):
        """Seconds since the epoch, as a float."""
        raise NotImplementedError

    # ---- the record plane (§99) — a host capability, not a program effect

    def record(self, entry):
        """Persist a record entry, if this host keeps one.

        Optional, unlike the five capabilities above: a host that does
        nothing here is still a complete host, and the interpreter must
        not depend on this happening. The default is a no-op.
        """

    # ---- foreign resolution

    def resolve(self, target):
        """Turn a foreign target string into something callable.

        The target is opaque to the language. A Python host reads
        `builtins.sorted`; a JavaScript host could read `node:fs#readFile`;
        a Rust host, a crate path. The *string* is host-specific by design,
        which is why no syntax change is needed to move hosts.
        """
        raise NotImplementedError

    def target_hint(self):
        """How this host wants a foreign target written, for error messages."""
        return "a name this host understands"

    # ---- data at the boundary

    def parse_json(self, text):
        raise NotImplementedError



class PythonHost(Host):
    """The host Planes runs on today.

    Chosen originally by default rather than by decision, and the decision
    is now recorded: it stays, because every requirement the language has
    accumulated is met here and the alternatives cost more than they return
    at this stage. See REPORT_HOST.md.
    """

    name = "python"

    def __init__(self):
        self._resolved = {}

    def ask(self, url):
        req = urllib.request.Request(
            url, headers={"User-Agent": "planes/0.1"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode()

    def read(self, path):
        with open(path) as f:
            return f.read()

    def write(self, path, text):
        with open(path, "w") as f:
            f.write(text)

    def show(self, text):
        print(text)

    def clock(self):
        import time
        return time.time()

    def resolve(self, target):
        import importlib
        if target in self._resolved:
            return self._resolved[target]
        mod_path, _, attr = target.rpartition(".")
        if not mod_path:
            raise HostError(f"bad target: {target}")
        try:
            fn = getattr(importlib.import_module(mod_path), attr)
        except (ImportError, AttributeError):
            raise HostError(f"cannot find '{target}'")
        self._resolved[target] = fn
        return fn

    def target_hint(self):
        return "`module.function`, e.g. `builtins.sorted`"

    def parse_json(self, text):
        return json.loads(text)



class TestHost(PythonHost):
    """A host with the outside world replaced.

    Not a mock bolted onto tests — a host, implementing the same five
    capabilities. That it can exist at all is the evidence that the seam is
    real rather than decorative, and it makes the whole test suite hermetic
    by construction instead of by discipline.
    """

    name = "test"

    def __init__(self, responses=None, files=None, now=None):
        super().__init__()
        self.responses = responses or {}
        self.files = dict(files or {})
        self.now = now if now is not None else 1_000_000.0
        self.shown = []
        self.recorded = []      # the record plane's in-memory sink

    def ask(self, url):
        r = self.responses
        if callable(r):
            return r(url)
        if url in r:
            return r[url]
        raise HostError(f"no stubbed response for {url}")

    def read(self, path):
        if path not in self.files:
            raise HostError(f"no such file: {path}")
        return self.files[path]

    def write(self, path, text):
        self.files[path] = text

    def show(self, text):
        self.shown.append(text)

    def clock(self):
        return self.now

    def record(self, entry):
        self.recorded.append(entry)
