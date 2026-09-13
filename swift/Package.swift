// swift-tools-version:6.0
// swift/Package.swift — Planes in Swift, the third host.
//
// A port of the reference (interp.py, parser.py, lexer.py and their modules),
// held to the same agreement suites the JavaScript host is: every
// test_swift_*.py at the repo root drives `planes-swift` and compares it with
// the Python implementation. No dependencies, like the other two hosts.
//
// HostRulesBench (H4) is a repo-internal timing tool, not part of the
// agreement suites and not a product: `swift run -c release HostRulesBench`
// (see swift/README.md). It is not in the root Package.swift (E3) — that
// manifest exposes only the two products a downstream consumer depends on.
import PackageDescription

let package = Package(
    name: "Planes",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "Planes", targets: ["Planes"]),
        .executable(name: "planes-swift", targets: ["PlanesCLI"]),
    ],
    targets: [
        .target(name: "Planes"),
        .executableTarget(name: "PlanesCLI", dependencies: ["Planes"]),
        .executableTarget(name: "HostRulesBench", dependencies: ["Planes"]),
    ]
)
