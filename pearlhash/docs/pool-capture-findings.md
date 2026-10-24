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


## Saved live notify and header research

The user displayed the saved independent-probe notify on 2026-10-24. Its four
fields are 400/64/16/1 characters, with the final string "3", as in capture 03.
This confirms the observed shape, not consensus version or target byte order.

Further isolated inspection allowed the legacy notify decoder to be called on
synthetic inputs without entering vendor mining main. For the inspected path it
returns 76 bytes from a 200-byte input, and controlled input-bit changes act as
byte-local XOR changes in the first 76 bytes; later bytes do not affect those
outputs. An additional repeating key step is present in client/device constants.
After that step, the older captured sample produces header-shaped bytes with
version 0x20000000, a timestamp matching the capture and plausible compact nbits.
The manually transcribed current sample produces the same version and a
plausible probe-session timestamp. This is a research candidate, not a complete
independent/general inner codec or a verified production job object. The full
transformation rule and the remaining 124 bytes are still unresolved. The
pinned official header layout is 4-byte LE version, two reversed 32-byte hashes,
4-byte LE timestamp and 4-byte LE nbits (proof_utils.rs). Structural plausibility
does not by itself prove header authenticity or consensus validity.

WildRig was additionally loaded in isolation only as far as the intercepted
startup hook, with socket/connect/send syscalls denied. Its mining main was not
entered. Constants/static data were inspected for the additional key step; no
vendor executable or code is included as a runtime dependency or redistributed.
This project continues to contain independent implementations, not a wrapper.

The legacy submission template mentions nonce, worker_nonce, miner_nonce,
m, n, k, tail_mode, rank, tile_h, tile_w, a_rows and b_cols. These names alone
are not proof of the current pool's accepted submission format or field
semantics. The next evidence needed is an actual existing-miner submit and its
correlated response; see [bounded capture decoding](share-capture.md).


## Capture 04: existing-miner submit/response observed on rig

The user's 2026-10-24 Termius screenshots report all three source checksums OK,
24 captured packets, zero kernel-dropped packets, ten decoded messages, three
outbound report_info requests and one outbound submit. Both directional streams
start mid-session, so their initial boundaries remain unverified. Decoder ran
to normal shell return. Reported PCAP SHA-256:
`7505454a4f614b530b8bfaca7bdba69784ef5129daff3f4a3c8724af8e90500f`.
The complete capture has not yet been transferred to the development host.

The submit id=866 has a unique matched response status=1,id=866,result=true.
This is a correlated successful existing-WildRig submission; it does not validate
a custom share. Actual params contain a_rows, b_cols, k, m, miner_nonce, n,
nonce, rank, sb, sb_p, tail_mode, tile_h, tile_w and worker_nonce.
Observed scalar values: m=5121,n=262144,k=32768,rank=128,tile_h=10,tile_w=16,
tail_mode=1,sb=1,sb_p=[]. The three named nonce fields are 16 hex characters
each. Their generation, byte order, job association and the sb/sb_p/tail_mode
semantics remain unresolved. This sample does not carry a serialized PlainProof
field; reproducing this pool's compact reconstruction contract is distinct from
sending arbitrary nonce/hash data or our offline PlainProof JSON.

Relative submitted rows expand as two contiguous entries at stride eight over
five groups; relative columns as two entries at stride eight in groups at
stride 32. The independent canonical PeriodicPattern implementation maps these
to 000103040000 and 000103010103 respectively, using the pinned upstream list/
byte rules. Tests use synthetic offsets; raw captured rows/nonces are not
published. The old offline runner now derives its existing eight-entry pattern
through this helper, producing the same six bytes as before. Three new CPU
pattern tests pass. No new GPU test, full job reconstruction or custom pool
submission is claimed by this change.

## Capture 04 verified transfer and ordered decoding

The complete 6,104-byte capture was subsequently reconstructed on the development
host. Both full SHA-256 values match the rig: raw PCAP
`7505454a4f614b530b8bfaca7bdba69784ef5129daff3f4a3c8724af8e90500f`, gzip
`f4a99536adde79e0efa9c56884f4a39862ea3161e6e65f0b65bbcbec85d84f77`.
The independent decoder reproduces 24 packets, ten messages and the unique
submit-866/status-1/true exchange. The submit becomes available at packet 5,
its response at packet 7, and the first captured notify at packet 15 (one-based
capture ordinals). Neither captured notify establishes the header for that share.

The decoder now retains nanosecond-normalized PCAP timestamps, packet ordinals
and per-stream line positions. Frames are ordered by the packet first making
all their TCP prefix bytes available. Identical retransmissions do not retime
frames; out-of-order gap filling can release multiple frames at once. Request
correlation rejects a reply observed before its request, independently of clock
values. This replaces the former direction-grouped report order.

## Independent notify/header component

`pool/job.py` implements the observed fixed-width notify schema and the first
76 bytes' two XOR stages, with no vendor runtime dependency. The first-stage
mapping was checked against 32 independent pseudorandom 200-byte payloads using
an isolated legacy decoder, in addition to earlier input-bit experiments. All
32 outputs match, including variation of the opaque trailing 124 bytes. The
same experiment confirms that the target field is copied as 32 decoded bytes;
it does not establish little/big-endian target comparison or pool scaling.
The second stage is the repeating 32-byte key step observed in the host path.
Experiments intercept startup, never enter vendor mining main, and deny network
syscalls. Neither vendor code nor research harnesses are shipped.

Header parsing follows pinned upstream's 76-byte serialization. The final
notify marker is retained as a marker, not silently converted into a consensus
version. Opaque trailing bytes and token are retained without guessed meanings.
This code reproduces a client header conversion; it is not authentication of a
pool header, a full pool job configuration or an accepted custom share.

`tools/capture_share_context.py` passively collects up to ten minutes/1,024
packets by default, stopping early after a unique accepted existing-miner submit
with preceding notification(s) on the same connection. All decoded records stay
local. Console prints only the last two preceding notify candidates plus that
submission/response. Timing does not establish which candidate supplied the
header; that requires reconstruction and mathematical/difficulty verification.
Notify field 3 is deliberately not equated with submitted worker_nonce.
No miner, service, clock, disk mount or pool selection is changed. Only the
newly created tcpdump process group is stopped. The capture and JSON are private
local files, never automatically uploaded.
