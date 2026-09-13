// main.swift — `planes-swift`, the agreement CLI.
//
// Mirrors js/cli.mjs's subcommands and output forms exactly, so each
// test_swift_*.py is its test_js_*.py counterpart with the command swapped.
// One file per command under this directory; this file only dispatches.
import Foundation
import Planes

let arguments = Array(CommandLine.arguments.dropFirst())
guard let sub = arguments.first else {
    CLI.fail("usage: planes-swift <command> [args]")
}
let rest = Array(arguments.dropFirst())

switch sub {
case "text": TextCommand.run(rest)
case "num": NumCommand.run(rest)
case "hash": HashCommand.run(rest)
default: CLI.fail("planes-swift: unknown or not yet ported command '\(sub)'")
}
