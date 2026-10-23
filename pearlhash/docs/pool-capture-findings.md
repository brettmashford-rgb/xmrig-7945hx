# Observed Pearlhash traffic — 2026-10-23

This records transport observations and subsequent independent decoding.
The outer JSON transport is now reproduced; inner job payload, target semantics
and share submission remain unresolved. Historical observations below are
retained with the decoding follow-up at the end.

## Capture 02 (existing live connection)

SHA-256: `f331acdf027201dacfbb7ace12aa6a15f69003f1f80cf52c43b74d4c5c6559ab`.
Original capture size 1,876 bytes; 14 packets; gzip transfer CRC checked.
Four payload-bearing packets contain complete newline-delimited ASCII hex:
two outbound lines (115 decoded bytes each) and two inbound lines (39 each).
The capture starts mid-session. The screenshots of WildRig show accepted shares,
but that alone does not identify the semantic meaning of these four messages.

## Capture 03 (fresh WildRig debug session)

SHA-256: `0a1f175985ce82f1ad0357372d1487d99f38b850bf0dff1e7507d359546d4939`.
Original capture size 4,637 bytes; 19 packets; gzip transfer CRC checked.
Observed complete ASCII-hex lines, after hex decoding:

| Direction | Decoded line sizes, in order |
|---|---|
| Miner to pool, first message | 131 bytes |
| Pool to miner, one TCP payload | 37, 67, 537 bytes |
| Pool to miner, next TCP payload | 537 bytes |
| Miner to pool | 113 bytes |
| Pool to miner | 37 bytes |

Hex decoding does not yield readable JSON. WildRig's debug log excerpt reports
two new jobs but does not expose the job contents. An additional encoding layer
appears present; it has not been identified or implemented. This capture does
not resemble ordinary plaintext NDJSON Stratum at the observed application layer.

## Operational outcome

The temporary debug executable exited on the planned SIGINT. The original
pearl.service returned active. Screenshot confirms the 2600 MHz runtime core
lock was restored. Saved autostart remains 2500 MHz core and 810 MHz memory.
No service file was edited. XMRig was not stopped by these commands.

## Open protocol requirements

Identify/decode the initial exchange, obtain version context, reconstruct the
exact job/header/config/target representation and produce the required proof
submission with its correlated pool verdict. Do not label arbitrary hex fields
as jobs or share acknowledgements based on length or timing alone.

If Pearlhash does not publish the encoding or client source, independently
decoding it or obtaining a compatible documented interface is additional work.
Using another pool for initial acceptance tests would require the user's pool
selection; it is not a silent substitute for Pearlhash compatibility.

Raw private-session captures are retained separately from this source release.

## Offline follow-up after GPU validation

The original captures were rechecked with the new standard-library-only
`tools/inspect_pool_capture.py`. It reads classic PCAP locally, reassembles
IPv4 TCP streams, checks retransmission overlaps/gaps, and inspects strict
newline-delimited ASCII hexadecimal. It makes no connections and does not
print wallet addresses, raw payloads or guessed field meanings.

Capture 03 reproduces 19 packets and directional decoded lengths
131/113 outbound and 37/67/537/537/37 inbound. Both directions include SYN,
all captured streams end at line boundaries, and no sequence gap or conflicting
retransmission is detected. Capture 02 reproduces 14 packets, outbound lengths
115/115 and inbound 39/39; its initial framing remains unverified because the
capture begins mid-session. Neither capture contains an incomplete final line.

In the 131-byte line and both 537-byte lines, skipping four decoded bytes and
comparing byte pairs 48 positions apart yields 100% agreement of the high bit.
That is a reproducible descriptive statistic. It is consistent with a repeating
mask over ASCII-like content, but does not identify an encoding, key derivation,
prefix format or plaintext. Exploratory guessed-plaintext decoding produced
ambiguous candidates, not a general validated decoder. No candidate field or
certificate version is accepted as protocol truth.

Public client artifacts were downloaded and checksum-checked on the development
host, initially for static inspection. Neither is redistributed. Later isolated
legacy encoder experiments are described below; WildRig was not executed:

- Pearlhash legacy V14 `pearl-miner`: publisher SHA-256
  `249696c9c91f8821d194219cbbe37f56df541c157fe3ddda2ff063aaf1c60e63`.
  https://github.com/pearlhash/pearlhash-miner/releases/tag/V14
- WildRig Multi 0.51.7 Linux archive: publisher SHA-256
  `29530c2d575491155649feb68f738215765889ca5b3d6b5bd81dda4d0dd58da1`.
  https://github.com/andru-kun/wildrig-multi/releases/tag/0.51.7

The inspected executable layouts expose little useful protocol text through
static string/section inspection. This did not resolve the codec. Other pools'
published JSON dialects are not evidence of this endpoint's deployed protocol.

Four synthetic analyzer tests pass: split/reordered/retransmitted lines,
sequence wrap, unknown initial boundary, and rejection of invalid hex,
truncation, missing initial bytes, gaps and conflicting overlaps. Supported
capture parsing is deliberately narrow; unsupported VLAN/fragmented traffic
and multiple sessions on one tuple fail explicitly. These are transport tests,
not protocol or share-verification tests.

Remaining blocker: a reproducible complete codec and exact handshake/job/proof
submission semantics for pool.pearlhash.xyz:9000. No fabricated shares were sent,
no pool connection was opened for these offline checks, and no pool was changed.


## Independent outer codec (after v0.0.5 rig confirmation)

After ASCII hex decoding, the first four bytes are a big-endian u32 nonce n.
For the 48 positive coefficients p listed in tools/pool_probe.py, the mask is
`(n * p - n % p) & 255`. XOR the remaining bytes with that repeating mask
and parse UTF-8 JSON. Encoding is the same XOR followed by hex and LF. This
obfuscation has no authentication and must not be treated as encryption.
Our encoder selects n in 10..0xfffffffe, avoiding observed legacy clamping
of values below 10 and 0xffffffff. The decoder applies the formula to any u32.
Input framing is strictly bounded and checked; duplicate JSON keys/nonfinite
numbers are rejected. This is an independently implemented Python codec;
there is no vendor executable/library/runtime dependency.

Evidence: all eleven messages from both captures decode consistently. Controlled
legacy encoder experiments additionally match 1,033 nonce cases each for a
192-byte repeated body, a two-byte `{}` body and every byte 0..255. Experiments
intercepted startup and exited without entering the vendor mining main;
socket/connect/send syscalls were denied by seccomp. Vendor binaries/research
harnesses and private captures are not included in this repository. A synthetic
nonce-10 encoder golden is in the tests. This is behavioral reconstruction,
not a claim that the pool has published an authoritative protocol specification.

Decoded capture 03:

- Outbound id=0 method=login, params=[wallet, worker, agent].
- Inbound status=1,id=0,result=true: login acknowledgement.
- Inbound status=1,id=-1,result=["extranonce", 16 hex characters].
- Two inbound status=1,id=-1,result arrays starting with "notify", followed
  by strings of 400,64,16,1 characters. The last is "3". We do not yet assign
  consensus version, header/config/target or work identity semantics to these.
- Outbound id=2 method=report_info, params contains reported GPU name/hashrate.
- Inbound status=1,id=2,result=true: report_info acknowledgement.

Capture 02 contains report_info requests id=255/257 and corresponding true
responses. Neither preserved capture contains a submit request or share verdict.
A notify's 400-character hex field decodes to 200 bytes with separate scrambling;
applying the outer codec again does not establish a meaningful job layout.

The login-only probe sends our own `pearlhash-dev/0.0.6-probe` agent, defaults
to the distinct `5060-dev-probe` worker and contacts only pool.pearlhash.xyz:9000.
It retains decoded messages locally; no transcript/wallet is automatically
uploaded. A login success establishes transport/login compatibility only.
It supplies neither production mining nor proof submission. The user's
2026-10-24 Termius screenshot confirms the independent live login, extranonce
and notify exchange passed on the rig, with source checksum OK.
