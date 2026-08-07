// js/world_recovery.mjs — recovery = replay. Mirrors world_recovery.py
// field for field; see that file's module docstring for the full
// rationale (why this reuses ReplayHost/trace directly through
// WorldRuntime's own host= constructor parameter rather than calling
// replay() itself, why a snapshot is an integrity checkpoint rather than a
// resume point, and the effect-scope note the module-load effect log
// below resolves for world_runtime_demo.planes specifically).

import { Interpreter, ReplayHost } from "./interp.mjs";
import { runFile } from "./run_file.mjs";
import { loadGrammar } from "./loader_node.mjs";
import { canonicalOutcomeString } from "./world_ir.mjs";
import { WorldRuntime } from "./world_runtime.mjs";
import { restoreSnapshot } from "./world_snapshot.mjs";
import { TestHost } from "./host.mjs";

export class WorldRecoveryError extends Error {
  constructor(tag, detail, fix) {
    super(`${tag}: ${detail}`);
    this.tag = tag;
    this.detail = detail;
    this.fix = fix;
  }
}

// The deterministic effect log runFile(path) ALONE produces — module-level
// statements only, before any world-init/advance call. Recomputed fresh
// each call; see world_recovery.py's `_module_load_effect_log`.
async function moduleLoadEffectLog(path) {
  loadGrammar();
  const loader = new Interpreter({ host: new TestHost(), record: true, trace: false });
  await runFile(loader, path);
  return loader.effectLog;
}

// Reconstruct the world value at snapshot.revision + ticksAfterSnapshot by
// deterministic replay of `path`'s world-init/advance. Refuses
// (WorldSnapshotError, propagated unchanged) if `snapshot` itself does not
// verify. Refuses (WorldRecoveryError) if replay, having reached the
// snapshot's own declared revision, produces a different canonical form
// than the snapshot claims. Returns the WorldRuntime at the reconstructed
// tick.
export async function recover(path, snapshot, ticksAfterSnapshot, { window = null, effectLog = null } = {}) {
  const { normalized: normalizedSnapshotEnvelope, revision: snapshotRevision } = restoreSnapshot(snapshot);

  const fullEffectLog = [...(await moduleLoadEffectLog(path)), ...(effectLog ?? [])];
  const host = new ReplayHost(fullEffectLog);
  const rt = new WorldRuntime(path, { host, window, trace: true });
  await rt.load();
  rt.init();
  for (let i = 0; i < snapshotRevision; i++) rt.advance();

  const { normalized: replayedEnvelope } = rt.envelope();
  const expected = canonicalOutcomeString(normalizedSnapshotEnvelope);
  const actual = canonicalOutcomeString(replayedEnvelope);
  if (actual !== expected) {
    throw new WorldRecoveryError(
      "snapshot-replay-divergence",
      "the snapshot's envelope does not match what deterministic replay of "
        + `'${path}' actually produces at revision ${snapshotRevision}`,
      "recover from an earlier snapshot that replay can actually reach, or "
        + "regenerate this snapshot from a real run of the program",
    );
  }

  for (let i = 0; i < ticksAfterSnapshot; i++) rt.advance();

  return rt;
}
