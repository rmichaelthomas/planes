// SHA256.swift — SHA-256 over a string's UTF-8 bytes.
//
// The Swift counterpart of js/sha256.mjs. rules.py fingerprints a rule with
// `hashlib.sha256(canonical.encode()).hexdigest()[:6]`, and a fingerprint
// appears in Planes source (the FINGERPRINT token the lexer recognizes). A
// fingerprint that differs by one byte between hosts makes source written by
// one invalid under the other, so this must be byte-identical to hashlib for
// arbitrary UTF-8 input. js/ carries the algorithm itself because
// crypto.subtle is async; Swift has a synchronous system implementation in
// CryptoKit, so this uses it. Verified against hashlib by test_swift_hash.py.
import CryptoKit
import Foundation

/// The 64-character lowercase hex SHA-256 digest of `s`'s UTF-8 bytes.
public func sha256Hex(_ s: String) -> String {
    let digest = SHA256.hash(data: Data(s.utf8))
    let hex: [UInt8] = Array("0123456789abcdef".utf8)
    var out: [UInt8] = []
    out.reserveCapacity(64)
    for byte in digest {
        out.append(hex[Int(byte >> 4)])
        out.append(hex[Int(byte & 0x0F)])
    }
    return String(decoding: out, as: UTF8.self)
}
