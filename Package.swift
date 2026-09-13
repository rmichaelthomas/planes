// swift-tools-version:6.0
// Package.swift — the root manifest.
//
// SwiftPM resolves a remote package dependency (`.package(url: ..., from:
// ...)`) only from a manifest at the repository root, never from a manifest
// in a subdirectory (Koncord v1.12 build prompt §2). Before this file, only
// swift/Package.swift existed, so Planes could not be added as a remote
// SwiftPM dependency at all.
//
// This manifest points at the same swift/Sources/... layout swift/Package.swift
// builds, and exposes the same products under the same names — `Planes` (the
// library) and `planes-swift` (the agreement CLI, PlanesCLI). It changes
// nothing about how the sources are organised: `cd swift && swift build`
// keeps working from swift/Package.swift unchanged, for local development
// and for the test_swift_*.py suites, which build by package path
// (see swift_host.py). This root manifest is for a downstream consumer that
// depends on this repository as a whole, by tag or by path.
//
// Platforms: .macOS(.v14) and .iOS(.v17). Checked before adding iOS: no
// `Process` anywhere in swift/Sources, no `#if os(macOS)`, and every
// FileManager use (Modules.swift, EffectSurfaceToolCommand.swift, CLI.swift)
// is ordinary path/file access available on iOS — nothing reads a home
// directory or anything else iOS sandboxes away at compile time. `swift
// build --triple arm64-apple-ios17.0` against the `Planes` product (this
// file's library target) succeeds; see swift/README.md for the caveat about
// PlanesCLI, which stays a macOS command-line executable in practice even
// though the platform list here is package-wide.
import PackageDescription

let package = Package(
    name: "Planes",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .library(name: "Planes", targets: ["Planes"]),
        .executable(name: "planes-swift", targets: ["PlanesCLI"]),
    ],
    targets: [
        .target(name: "Planes", path: "swift/Sources/Planes"),
        .executableTarget(name: "PlanesCLI", dependencies: ["Planes"], path: "swift/Sources/PlanesCLI"),
    ]
)
