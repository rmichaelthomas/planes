# Horizon Phase 1 — renderer pipeline verification

| Check | Description | Result |
|---|---|---|
| A | a delta produced in the worker reaches the performer and moves the placeholder to the worker's own final envelope position | PASS |
| B1 | semantic determinism — identical snapshot/delta hash sequence across two fresh runs of the same fixture | PASS |
| B2 | quality-tier invariance — identical semantic hash sequence whether or not fidelity tiers are switched mid-run | PASS |
| C | a deliberately delayed/reordered message is discarded, not applied; sequence monotonicity holds | PASS |
| D | horizon.html and every new module load with no npm/CDN/bundle; Pixi vendor provenance file present and complete | PASS |
| E | horizon.html carries the placeholder banner; results file (once produced) states visual acceptance is Phase-2-owed; no new image asset was added beyond the known diagnostic screenshots | PASS |
| F | kernel and core untouched — git diff --name-only main on world_kernel.*/interp.*/value-model/grammar shows nothing | PASS |
| G | Sun-provisional frame-time distributions recorded with a Phase-2 recalibration note | PASS |

## Detail

**A** (PASS): deltas=8 finalSituation={"containingPlace":"reso-landing-cell","space":"world","x":0.35,"y":4.013,"state":"standing","occupancy":3,"anchorId":"anchor-reso-1","chunkActive":true,"physicsRef":"phys-reso-1","audioRef":"audio-reso-1"} lastAppliedScreen={"x":104.49999999999997,"y":322.20000000000005}
**B1** (PASS): run1[0..2]=8a9248dfa04e2300cb27f3612178a6fd436f0efa710d857a1558ecaac0e77235,4487dc436a7f0e565a5bb62476ff6fbd1ee0cc168aa215fadf8a33a0c6facacd run2[0..2]=8a9248dfa04e2300cb27f3612178a6fd436f0efa710d857a1558ecaac0e77235,4487dc436a7f0e565a5bb62476ff6fbd1ee0cc168aa215fadf8a33a0c6facacd len1=12 len2=12
**B2** (PASS): tiersExercised=sun,breeze,harbor tieredLen=12
**C** (PASS): admits=[true,true,false,false,true] lastAppliedSequence=3 discardedCount=2
**D** (PASS): horizonStatus=200 noCdnScript=true allFilesLoad=true vendorMdComplete=true noPackageJson=true fetchResults=[["js/world/runtime/worker.mjs",200],["js/world/runtime/main.mjs",200],["js/world/performers/pixi_performer.mjs",200],["js/world/performers/dom_mirror.mjs",200],["js/world/performers/fidelity_controller.mjs",200],["js/world/performers/safe_harbor.mjs",200],["js/world/performers/frame_bench.mjs",200],["js/vendor/pixi/pixi.min.mjs",200]]
**E** (PASS): hasBanner=true noNewArt=true resultsExists=true resultsDisclosesPhase2=true imageFiles=["horizon-renderer-pipeline-capture-pixi.png","horizon-renderer-pipeline-capture-safe-harbor.png"] unexplainedImages=[]
**F** (PASS): (empty diff, as required)
**G** (PASS): hasDistributions=true hasSunProvisional=true hasRecalibrationNote=true
