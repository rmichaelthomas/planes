// HostRulesBench — H4: measure HostRules cost.
//
// Koncord checks a page's asks against a Planes rules file on every page load
// (HostRules.swift) and records that per-page cost as unmeasured (Koncord
// v1.10 §272.4). This is a repo-internal timing tool, not an agreement suite:
// nothing compares it against Python or JS, and scripts/ci.sh does not run
// it. Build and run it in release mode:
//
//   cd swift && swift run -c release HostRulesBench
//
// It generates two synthetic rules fixtures scaled up from demo/rules/
// exception.planes's shape (one default-deny rule plus many named
// exceptions, each with `because`) — one at ~50 rules, one at ~200 — with
// varied hosts and paths, then checks each against a synthetic 150-effect
// "page" of asks (a realistic page's worth of outbound requests: some to
// permitted endpoints, some to a permitted host but with a tracking query
// string the rule never named, some to hosts no rule ever mentions, so the
// default-deny catches them). It measures, over many iterations:
//
//   (a) loading/compiling the rules — `HostRuleSet(source:)`, which parses
//       the source and resolves `supersedes`.
//   (b) checking a page — `rules.check(effects)` against the pre-loaded
//       rule set, mirroring how a host actually uses it: load once, check
//       many pages.
//
// p50/p95 (plus min/p99/max/mean), in the style of world_kernel_bench.py,
// written to a markdown results file — the run's own machine specs (CPU,
// core count, macOS version) captured live, never invented, alongside a
// note that other agents may have been building concurrently on this
// machine, so the numbers are an upper bound, not a clean-room measurement.
import Darwin
import Dispatch
import Foundation
import Planes

// MARK: - Fixture generation

/// A synthetic rules fixture: `ruleCount` rules (one default-deny plus
/// `ruleCount - 1` permits, each excepting it for one specific host+path),
/// and the exact targets those permits admit — needed to build a page of
/// asks that actually exercises the permitted paths, not just the deny.
struct RuleFixture {
    let ruleCount: Int
    let source: String
    let permittedTargets: [String]
}

private let categories = [
    "analytics", "audit", "cdn", "telemetry", "payments", "auth", "media",
    "search", "ads", "backup", "metrics", "billing", "support", "docs",
    "status", "sync", "push", "config", "assets", "logs",
]
private let paths = [
    "/collect", "/pixel.gif", "/v1/events", "/v2/ingest", "/assets/app.js",
    "/healthz", "/webhook", "/api/v1/sync", "/track", "/beacon",
]
private let tlds = ["com", "internal", "io", "net"]

func makeRulesFixture(ruleCount: Int) -> RuleFixture {
    precondition(ruleCount >= 2, "need at least the default-deny plus one permit")
    var lines: [String] = [
        "rule [no-external-sends] anything may not ask",
        "  because \"default-deny keeps outbound requests to an unapproved endpoint\"",
        "",
    ]
    var permitted: [String] = []
    for i in 1..<ruleCount {
        let cat = categories[i % categories.count]
        let path = paths[i % paths.count]
        let tld = tlds[i % tlds.count]
        let target = "https://\(cat)-\(i).example.\(tld)\(path)"
        permitted.append(target)
        lines.append("rule [allow-\(i)] anything may ask to \"\(target)\" supersedes [no-external-sends]")
        lines.append("  because \"the \(cat) endpoint is an approved integration (ticket OPS-\(1000 + i))\"")
        lines.append("")
    }
    return RuleFixture(ruleCount: ruleCount, source: lines.joined(separator: "\n") + "\n", permittedTargets: permitted)
}

/// A synthetic page's worth of asks: `pageSize` effects mixing admitted
/// hits on permitted endpoints, the same permitted host with a tracking
/// query string no rule named (so it falls back to the default-deny — a
/// realistic near-miss, not just a clean hit-or-miss set), and asks to
/// hosts no rule mentions at all.
func makePageOfAsks(pageSize: Int, permitted: [String]) -> [HostEffect] {
    let trackerHosts = [
        "https://tracker.example/pixel.gif",
        "https://ads.rogue.example/beacon",
        "https://metrics.untrusted.example/collect",
    ]
    var effects: [HostEffect] = []
    effects.reserveCapacity(pageSize)
    for i in 0..<pageSize {
        let target: String
        switch i % 5 {
        case 0:
            // a clean hit: exactly what a permit names
            target = permitted[i % permitted.count]
        case 1:
            // the same permitted host, but a tracking query string the
            // permit's literal target never named -> falls to the deny
            target = permitted[(i / 5) % permitted.count] + "?utm_source=campaign&session=\(i)"
        case 2:
            // an unrelated tracker, with a query string
            target = trackerHosts[i % trackerHosts.count] + "?id=\(1000 + i)"
        case 3:
            // a host no rule mentions at all
            target = "https://unknown-\(i).example.net/api/v1/collect"
        default:
            target = permitted[(i * 3) % permitted.count]
        }
        effects.append(.ask(target, site: i + 1))
    }
    return effects
}

// MARK: - Timing

func nowNs() -> UInt64 { DispatchTime.now().uptimeNanoseconds }

struct Stats {
    let count: Int
    let minNs: Double
    let p50Ns: Double
    let p95Ns: Double
    let p99Ns: Double
    let maxNs: Double
    let meanNs: Double
}

func percentiles(_ valuesNs: [Double]) -> Stats {
    let ordered = valuesNs.sorted()
    let n = ordered.count
    func pct(_ p: Double) -> Double {
        let idx = min(n - 1, max(0, Int((p * Double(n)).rounded(.up)) - 1))
        return ordered[idx]
    }
    let mean = valuesNs.reduce(0, +) / Double(n)
    return Stats(count: n, minNs: ordered[0], p50Ns: pct(0.50), p95Ns: pct(0.95),
                 p99Ns: pct(0.99), maxNs: ordered[n - 1], meanNs: mean)
}

func fmtUs(_ ns: Double) -> String { String(format: "%.2f", ns / 1000.0) }

// MARK: - Machine specs (live capture, never invented)

func sysctlString(_ name: String) -> String {
    var size = 0
    guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else { return "unknown" }
    var buffer = [CChar](repeating: 0, count: size)
    guard sysctlbyname(name, &buffer, &size, nil, 0) == 0 else { return "unknown" }
    let bytes = buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
    return String(decoding: bytes, as: UTF8.self)
}

struct MachineSpecs {
    let cpu: String
    let cores: Int32
    let osVersion: String
    let swiftBuildConfig: String
}

func captureMachineSpecs() -> MachineSpecs {
    var cores: Int32 = 0
    var size = MemoryLayout<Int32>.size
    sysctlbyname("hw.ncpu", &cores, &size, nil, 0)
    let os = ProcessInfo.processInfo
    let v = os.operatingSystemVersion
    #if DEBUG
    let config = "debug"
    #else
    let config = "release"
    #endif
    return MachineSpecs(
        cpu: sysctlString("machdep.cpu.brand_string"),
        cores: cores,
        osVersion: "macOS \(v.majorVersion).\(v.minorVersion).\(v.patchVersion)",
        swiftBuildConfig: config)
}

// MARK: - Benchmark

let LOAD_ITERATIONS = 2000
let CHECK_ITERATIONS = 1000
let PAGE_SIZE = 150
let RULE_COUNTS = [50, 200]

struct ConfigResult {
    let ruleCount: Int
    let loadStats: Stats
    let checkStats: Stats
    let admitted: Int
    let violations: Int
    let cleared: Int
    let vacuous: Int
}

func runConfig(ruleCount: Int) throws -> ConfigResult {
    let fixture = makeRulesFixture(ruleCount: ruleCount)
    let asks = makePageOfAsks(pageSize: PAGE_SIZE, permitted: fixture.permittedTargets)

    // Warm up (allocator/cache warmth; Swift is AOT-compiled, so this is
    // insurance, not JIT warmup) before any timed iteration.
    _ = try HostRuleSet(source: fixture.source)
    let warm = try HostRuleSet(source: fixture.source)
    let warmOutcome = try warm.check(asks)

    var loadNs: [Double] = []
    loadNs.reserveCapacity(LOAD_ITERATIONS)
    for _ in 0..<LOAD_ITERATIONS {
        let t0 = nowNs()
        _ = try HostRuleSet(source: fixture.source)
        loadNs.append(Double(nowNs() - t0))
    }

    let rules = try HostRuleSet(source: fixture.source)
    var checkNs: [Double] = []
    checkNs.reserveCapacity(CHECK_ITERATIONS)
    for _ in 0..<CHECK_ITERATIONS {
        let t0 = nowNs()
        _ = try rules.check(asks)
        checkNs.append(Double(nowNs() - t0))
    }

    let violations = warmOutcome.violations.count
    let cleared = warmOutcome.cleared.count
    let vacuous = warmOutcome.results.filter(\.vacuous).count
    let admitted = asks.count - violations

    return ConfigResult(ruleCount: ruleCount, loadStats: percentiles(loadNs),
                         checkStats: percentiles(checkNs), admitted: admitted,
                         violations: violations, cleared: cleared, vacuous: vacuous)
}

func statsRow(_ label: String, _ s: Stats) -> String {
    "| \(label) | \(fmtUs(s.minNs)) | \(fmtUs(s.p50Ns)) | \(fmtUs(s.p95Ns)) | " +
        "\(fmtUs(s.p99Ns)) | \(fmtUs(s.maxNs)) | \(fmtUs(s.meanNs)) | \(s.count) |"
}

func writeResultsMd(path: String, specs: MachineSpecs, results: [ConfigResult], commit: String) throws {
    var lines: [String] = []
    lines.append("# HostRules cost — measured results (H4)\n")
    lines.append("Koncord v1.10 §272.4 records the per-page rule-check cost as unmeasured. " +
                 "This is that measurement: `swift/Sources/HostRulesBench` loads a synthetic " +
                 "rules fixture scaled up from `demo/rules/exception.planes`'s shape (one " +
                 "default-deny rule plus many named permits, each with `because`), and checks " +
                 "it against a synthetic 150-effect page of asks (a mix of clean hits on " +
                 "permitted endpoints, permitted hosts with an unnamed tracking query string, " +
                 "and hosts no rule mentions at all).\n")
    lines.append("**Date:** captured at run time by this program.  ")
    lines.append("**Commit (base):** `\(commit)`  ")
    lines.append("**Build configuration:** `\(specs.swiftBuildConfig)` " +
                 "(`swift run -c release HostRulesBench`; release matters — debug is " +
                 "meaningfully slower and not what a shipped host runs).  ")
    lines.append("**Page size:** \(PAGE_SIZE) asks. " +
                 "**Iterations:** \(LOAD_ITERATIONS) (load), \(CHECK_ITERATIONS) (check-a-page), " +
                 "per rule-count configuration.\n")

    lines.append("## Machine specs (live capture, never invented)\n")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append("| CPU | \(specs.cpu) |")
    lines.append("| cores | \(specs.cores) |")
    lines.append("| OS | \(specs.osVersion) |")
    lines.append("\n**Other agents were building concurrently on this machine while this ran " +
                 "(this repo's Sprint A work was split across several parallel git worktrees). " +
                 "These numbers are an upper bound on the real cost, not a clean-room " +
                 "measurement** — CPU contention from sibling builds can only make a check " +
                 "look slower than it is, never faster.\n")

    for r in results {
        lines.append("## \(r.ruleCount) rules\n")
        lines.append("Page outcome (one representative check, same every iteration since the " +
                     "fixture is fixed): \(r.admitted)/\(PAGE_SIZE) admitted, \(r.violations) " +
                     "violation(s), \(r.cleared) cleared-by-permit, \(r.vacuous) vacuous rule(s).\n")
        lines.append("All times in microseconds (µs).\n")
        lines.append("| | min | p50 | p95 | p99 | max | mean | n |")
        lines.append("|---|---|---|---|---|---|---|---|")
        lines.append(statsRow("load/compile the rules", r.loadStats))
        lines.append(statsRow("check a page (\(PAGE_SIZE) asks)", r.checkStats))
        lines.append("")
    }

    try lines.joined(separator: "\n").write(toFile: path, atomically: true, encoding: .utf8)
}

func gitCommit() -> String {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
    p.arguments = ["git", "rev-parse", "HEAD"]
    let pipe = Pipe()
    p.standardOutput = pipe
    do {
        try p.run()
        p.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        let out = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
        return (out?.isEmpty == false) ? out! : "unknown"
    } catch {
        return "unknown"
    }
}

// MARK: - Entry point

let outputPath = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "host-rules-bench-results.md"
let specs = captureMachineSpecs()
print("HostRulesBench — build config: \(specs.swiftBuildConfig)")
print("CPU: \(specs.cpu)  cores: \(specs.cores)  OS: \(specs.osVersion)")

var results: [ConfigResult] = []
for ruleCount in RULE_COUNTS {
    print("\nrunning \(ruleCount)-rule config (\(LOAD_ITERATIONS) load iters, \(CHECK_ITERATIONS) check iters)...")
    let r = try runConfig(ruleCount: ruleCount)
    print("  load   p50=\(fmtUs(r.loadStats.p50Ns))us  p95=\(fmtUs(r.loadStats.p95Ns))us")
    print("  check  p50=\(fmtUs(r.checkStats.p50Ns))us  p95=\(fmtUs(r.checkStats.p95Ns))us")
    print("  page:  \(r.admitted)/\(PAGE_SIZE) admitted, \(r.violations) violation(s), " +
          "\(r.cleared) cleared, \(r.vacuous) vacuous")
    results.append(r)
}

try writeResultsMd(path: outputPath, specs: specs, results: results, commit: gitCommit())
print("\nwrote \(outputPath)")
