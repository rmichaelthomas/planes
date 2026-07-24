# What inertness covers

The annotation plane's guarantee (unbound v1.0 §4 item 3, §218) is that a `because`
clause or a `note:` block cannot change what a program *does*. "Does" means the
effect vocabulary lexer.py's `EFFECT_KINDS` closes over: `show`, `write`, `ask`,
`read`, `clock`, `random`, `env` — the boundaries a program crosses, logged at
runtime in `Interpreter.effects` and predicted statically by `shapes.py`'s effect
surface. Those are what `test_annotation.py`'s inertness test compares, byte-for-byte,
between an annotated program and the same program with every annotation stripped.

`why` is not in that vocabulary. It is the derivation query — unbound v1.1 §21's
second guarantee, an inspection facility a reader invokes on request, not a boundary
the program crosses on its own. `why cap` does not write a file, does not touch the
network, does not appear in `Interpreter.effects` at all. It only prints to the same
place `show` does, which is why the distinction needs stating rather than assumed:
both end up as strings in `Interpreter.output`.

So `why` displaying a `because` (§1.5 of the annotation-plane build) is not a hole in
inertness — it is the feature. The annotation carries the *why*; showing it on request
is the point, the same way `why`'s existing derivation trace is not itself an effect
just because it is text on a screen. An annotation changing what a program *emits* via
`show`/`write`/`ask`/`read` would be the guarantee broken. An annotation changing what
an inspection tool *displays when asked* is the guarantee working as designed.

**The rule:** inertness governs effects, not inspection. `test_annotation.py`'s
`run_and_capture` enforces this directly — it compares show-output (effects of kind
`"show"`), the full effect log, and the static effect surface between an annotated
run and a stripped run, and requires all three identical. `why`'s output is captured
separately and is allowed, and in
`test_why_on_an_annotated_binding_does_not_break_inertness` explicitly shown, to
differ.

This is a lock, not an implementation detail — noted as owed by
`REPORT_ANNOTATION.md` §6 item 1, closed here rather than left implicit.
