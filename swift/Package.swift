// swift-tools-version:6.0
// swift/Package.swift — Planes in Swift, the third host.
//
// A port of the reference (interp.py, parser.py, lexer.py and their modules),
// held to the same agreement suites the JavaScript host is: every
// test_swift_*.py at the repo root drives `planes-swift` and compares it with
// the Python implementation. No dependencies, like the other two hosts.
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
    ]
)
