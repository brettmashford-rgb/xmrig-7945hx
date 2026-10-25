# Pearlhash protocol findings

The independent transport codec, login probe, notify/header conversion and
local capture tools are implemented under this project's ISC license. This
file documents protocol behavior and validation scope. Private captures,
fingerprints, nonces and derived session outputs remain on the user's rig.

## Outer transport

Messages are newline-delimited ASCII hexadecimal. Hex decoding yields a
four-byte big-endian u32 nonce followed by XOR-obfuscated UTF-8 JSON. For the
48 coefficients in `tools/pool_probe.py`, mask byte i is
`(nonce * coefficient[i] - nonce % coefficient[i]) & 255`.
The mask repeats every 48 bytes. This is obfuscation, not authentication.
Strict bounded parsing rejects malformed hex/UTF-8, duplicate JSON keys and
nonfinite numbers. Do not treat this endpoint as ordinary plaintext Stratum.

Independent login, extranonce and notify decoding passed on the rig. Login
success is not a share verdict. The notify result has a fixed 200-byte payload,
32-byte target field, 8-byte opaque token and observed version marker. Neither
message lengths nor timing alone establish field semantics or share identity.

## Header and compact signals

`pool/job.py` implements the independently observed first-76-byte conversion
and repeating mask, preserving the remaining payload bytes. Controlled
synthetic cases match the inspected decoder. Structural decoding is not
consensus validation; a version marker alone must not choose consensus rules.

The supported local dense replay profile has an enabled `sb` flag, empty
`sb_p`, tail mode 1 and rank 128. For that profile the constant signal fill is
64. The final 16 A bytes come from the independently implemented nonce mapping.
`sb` must not be interpreted as the literal fill byte. Unsupported profiles
fail explicitly. No FP8 algorithm change is inferred.

A saved existing-miner case now reconstructs below its selected target using
explicit V3 seeds. Full commitments and sparse openings authenticate with the
independent CPU implementation, and selected math matches the independent C++
checker. The saved replay's GPU math and official CPU proof verification now pass on
the rig, confirmed by its completed local manifest.
This does not establish every live job/version/target rule or custom acceptance.

## Local evidence and replay

The capture decoder reassembles supported IPv4 TCP flows, checks conflicting
retransmissions and gaps, and orders frame availability by packet dependencies.
Typed request IDs and connection identity correlate recorded responses.
Preceding notifications are candidates until mathematical verification binds
one to the submission; the opaque notify token is not assumed to be a worker
nonce or job identifier.

`tools/replay_pool_context.py` reads an existing local context selected by
caller-provided record IDs and a local SHA-256 expectation. It makes no network
connection and never resends a recorded submit. No private capture or derived
session reference is distributed. The tool streams constant matrix hashes and
sparse proofs, runs the previously validated GPU math checker, and requires the
pinned official CPU verifier. Exact nBits conversion avoids target rounding.

The working pool remains pool.pearlhash.xyz:9000. No alternate pool is selected.
No custom share has been submitted/accepted, no production search is implemented,
and no speed/power improvement is measured. Services, clocks and autostart remain
unchanged. Synthetic V2/V3 GPU-leaf-to-proof validation is recorded separately.



## Explicit profile and job-state checkpoint (v0.0.20)

The saved metadata inspection is complete. Raw and both diagnostic XOR views
have no exact match to the verified replay configuration; no field interpretation
is inferred from those unsuccessful views. Reference GPU setup consumes a
76-byte header and builds its 52-byte config separately. The new independent
adapter accepts an explicit V3/rank128 dense profile instead of pretending the
opaque tail supplies a decoded configuration.

Job-key and little-endian scaled-target calculations can now be checked directly
against the completed local replay facts without repeating its expensive proof.
A separate saved independent-login exchange exercises login/extranonce/notify
readiness, then controlled replacement/reset invalidates stale work. Five CPU
unit tests and isolated synthetic-input integration pass. Real saved-input rig
integration is pending. No new live connection or submitted share is made.
The assigned-extranonce role in compact submit remains unverified, as do token/
metadata meanings and broader deployed-version rules. Neither marker3 alone nor
an offline fixture is a pool share verdict.
