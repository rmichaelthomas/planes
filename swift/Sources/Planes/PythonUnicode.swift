// PythonUnicode.swift — Python's text operations, at Python's Unicode version.
//
// shapes.py folds `lower of`, `upper of` and `normalize of` a known value with
// Python's str.lower, str.upper and unicodedata.normalize("NFC", ...), and reads
// a known list or record as Python's repr, which escapes what str.isprintable()
// refuses. None of these can come from the platform (swift/README.md rule 5):
// Swift's Unicode.Scalar properties are the OS runtime's, so they move with the
// macOS version the library runs on, and Foundation's normalisation lacks
// Unicode 16's composites and drops code points from a long run of combining
// marks ("a" + 63 × U+0301 + U+0340 loses the U+0340). The
// data is Python's own, generated into Generated/PythonUnicodeData.swift by
// scripts/swift_unicode_gen.py; this file is the algorithms over it, as CPython
// runs them. test_swift_shapes.py drives every code point through all four
// against the running Python.

// ================================================================ lookups

/// Is `v` inside one of the inclusive (low, high) pairs of `flat`?
private func inPairs(_ flat: [UInt32], _ v: UInt32) -> Bool {
    var lo = 0
    var hi = flat.count / 2
    while lo < hi {
        let mid = (lo + hi) / 2
        if v < flat[2 * mid] { hi = mid } else if v > flat[2 * mid + 1] { lo = mid + 1 } else { return true }
    }
    return false
}

/// The scalars `v` maps to in a (keys, starts, values) table, or nil.
private func mapped(_ keys: [UInt32], _ starts: [UInt32], _ values: [UInt32], _ v: UInt32) -> ArraySlice<UInt32>? {
    var lo = 0
    var hi = keys.count
    while lo < hi {
        let mid = (lo + hi) / 2
        if v < keys[mid] { hi = mid } else if v > keys[mid] { lo = mid + 1 } else {
            return values[Int(starts[mid])..<Int(starts[mid + 1])]
        }
    }
    return nil
}

private func appendScalars(_ out: inout String, _ values: ArraySlice<UInt32>) {
    for v in values { out.unicodeScalars.append(Unicode.Scalar(v)!) }
}

// ================================================================ printable, case

/// Python's `str.isprintable()` for one character.
func pythonIsPrintable(_ c: Unicode.Scalar) -> Bool {
    !inPairs(PythonUnicodeData.notPrintable, c.value)
}

private func isCaseIgnorable(_ v: UInt32) -> Bool { inPairs(PythonUnicodeData.caseIgnorable, v) }
private func isCased(_ v: UInt32) -> Bool { inPairs(PythonUnicodeData.cased, v) }

/// CPython's `handle_capital_sigma`: U+03A3 lowers to final sigma when a cased
/// character precedes it, past any case-ignorable ones, and none follows it.
private func finalSigma(_ cps: [UInt32], _ i: Int) -> Bool {
    var j = i - 1
    var c: UInt32 = 0
    while j >= 0 {
        c = cps[j]
        if !isCaseIgnorable(c) { break }
        j -= 1
    }
    var final = j >= 0 && isCased(c)
    if final && i + 1 < cps.count {
        j = i + 1
        while j < cps.count {
            c = cps[j]
            if !isCaseIgnorable(c) { break }
            j += 1
        }
        final = j == cps.count || !isCased(c)
    }
    return final
}

/// Python's `str.lower()`.
func pythonLower(_ s: String) -> String {
    let cps = s.unicodeScalars.map(\.value)
    var out = ""
    for (i, v) in cps.enumerated() {
        if v == 0x3A3 {
            out.unicodeScalars.append(finalSigma(cps, i) ? "\u{3C2}" : "\u{3C3}")
        } else if let m = mapped(PythonUnicodeData.lowerKeys, PythonUnicodeData.lowerStarts,
                                 PythonUnicodeData.lowerValues, v) {
            appendScalars(&out, m)
        } else {
            out.unicodeScalars.append(Unicode.Scalar(v)!)
        }
    }
    return out
}

/// Python's `str.upper()`.
func pythonUpper(_ s: String) -> String {
    var out = ""
    for c in s.unicodeScalars {
        if let m = mapped(PythonUnicodeData.upperKeys, PythonUnicodeData.upperStarts,
                          PythonUnicodeData.upperValues, c.value) {
            appendScalars(&out, m)
        } else {
            out.unicodeScalars.append(c)
        }
    }
    return out
}

// ================================================================ NFC

private let S_BASE: UInt32 = 0xAC00, L_BASE: UInt32 = 0x1100, V_BASE: UInt32 = 0x1161, T_BASE: UInt32 = 0x11A7
private let L_COUNT: UInt32 = 19, V_COUNT: UInt32 = 21, T_COUNT: UInt32 = 28
private let N_COUNT = V_COUNT * T_COUNT, S_COUNT = L_COUNT * N_COUNT

private func combiningClass(_ v: UInt32) -> UInt32 {
    let flat = PythonUnicodeData.combiningClass
    var lo = 0
    var hi = flat.count / 3
    while lo < hi {
        let mid = (lo + hi) / 2
        if v < flat[3 * mid] { hi = mid } else if v > flat[3 * mid + 1] { lo = mid + 1 } else { return flat[3 * mid + 2] }
    }
    return 0
}

private func primaryComposite(_ a: UInt32, _ b: UInt32) -> UInt32? {
    // Hangul: L + V -> LV, LV + T -> LVT.
    if a >= L_BASE && a < L_BASE + L_COUNT && b >= V_BASE && b < V_BASE + V_COUNT {
        return S_BASE + ((a - L_BASE) * V_COUNT + (b - V_BASE)) * T_COUNT
    }
    if a >= S_BASE && a < S_BASE + S_COUNT && (a - S_BASE) % T_COUNT == 0 && b > T_BASE && b < T_BASE + T_COUNT {
        return a + (b - T_BASE)
    }
    let flat = PythonUnicodeData.composites
    var lo = 0
    var hi = flat.count / 3
    while lo < hi {
        let mid = (lo + hi) / 2
        let (x, y) = (flat[3 * mid], flat[3 * mid + 1])
        if a < x || (a == x && b < y) { hi = mid } else if a > x || b > y { lo = mid + 1 } else { return flat[3 * mid + 2] }
    }
    return nil
}

/// Python's `unicodedata.normalize("NFC", s)`: full canonical decomposition,
/// canonical ordering, then canonical composition, each as UAX #15 defines it.
func pythonNFC(_ s: String) -> String {
    // Decompose.
    var d: [UInt32] = []
    d.reserveCapacity(s.unicodeScalars.count)
    for c in s.unicodeScalars {
        let v = c.value
        if v >= S_BASE && v < S_BASE + S_COUNT {
            let i = v - S_BASE
            d.append(L_BASE + i / N_COUNT)
            d.append(V_BASE + (i % N_COUNT) / T_COUNT)
            if i % T_COUNT != 0 { d.append(T_BASE + i % T_COUNT) }
        } else if let m = mapped(PythonUnicodeData.decompositionKeys, PythonUnicodeData.decompositionStarts,
                                 PythonUnicodeData.decompositionValues, v) {
            d.append(contentsOf: m)
        } else {
            d.append(v)
        }
    }

    // Order each run of non-starters by class, stably.
    let classes = d.map(combiningClass)
    var i = 0
    while i < d.count {
        if classes[i] == 0 {
            i += 1
            continue
        }
        var j = i
        while j < d.count && classes[j] != 0 { j += 1 }
        if j - i > 1 {
            let run = (i..<j).sorted { a, b in classes[a] != classes[b] ? classes[a] < classes[b] : a < b }
            let reordered = run.map { d[$0] }
            d.replaceSubrange(i..<j, with: reordered)
        }
        i = j
    }

    // Compose: a character joins the last starter unless something between
    // them blocks it — a starter, or a character of the same or higher class.
    var out: [UInt32] = []
    out.reserveCapacity(d.count)
    var starter: Int?
    var lastClass: UInt32 = 0
    for v in d {
        let cls = combiningClass(v)
        if let s = starter {
            let adjacent = out.count - 1 == s
            if adjacent || (lastClass != 0 && lastClass < cls), let composite = primaryComposite(out[s], v) {
                out[s] = composite
                continue
            }
        }
        if cls == 0 { starter = out.count }
        lastClass = cls
        out.append(v)
    }

    var text = ""
    for v in out { text.unicodeScalars.append(Unicode.Scalar(v)!) }
    return text
}
