# Decode an existing miner's submission

The independent login probe passed on the user's original pool. Neither older
capture contains a submit. To determine the real submission format, capture
existing WildRig traffic without stopping or restarting it, then run
`tools/decode_pool_capture.py CAPTURE --output NEW_JSON_PATH`.

The decoder uses the sibling `inspect_pool_capture.py` and `pool_probe.py`;
all three are Python standard library only. It makes no connections and sends
nothing. Classic PCAP/SLL2/SLL/Ethernet IPv4 support, TCP reassembly and explicit
failure on gaps/conflicting retransmissions are reused from the analyzer.
It bounds files at 32 MiB and streams/encoded frames at 8 MiB. The live login
probe retains its smaller 64 KiB limit. Initial mid-session boundary uncertainty
and omitted incomplete end fragments are reported. Complete malformed interior
frames fail; only an undecodable initial mid-session fragment may be omitted.

Requests/responses are grouped by the same TCP endpoint tuple, direction and
exact typed request id. Duplicate request/response ids are flagged ambiguous,
with no matched response selected. Console prints at most three submit requests
and their unique matching responses. Large arrays/strings are summarized; the
complete decoded messages stay in a new local mode-0600 JSON file. Login params
are not automatically printed. Records preserve directional sequence order;
the report is not a global chronological replay or a performance benchmark.

A response to report_info is never classified as a share result. No unknown
message is labeled by size/timing. The request method must actually be submit.
A captured existing-miner success cannot validate our independent miner.

The rig command bounds collection to five minutes or 256 packets on TCP port
9000, and retains raw PCAP locally. It uses tcpdump with sudo, drops capture
privileges to the rig user, and changes no service, clock or mining setting.
Port filtering observes the already established connection without a DNS guess
about its peer. The decoder separates connection tuples. If no submit occurs
within the capture, it reports that explicitly; no acknowledgement is inferred.
No raw capture or private decoded transcript is published to GitHub.

Five decoder tests cover fragmented messages, report/submit distinction,
negative responses, connection/id separation, ambiguous duplicates, partial
boundaries, malformed data/gaps and large proof-size frames. Alongside the
existing framing and login tests, fourteen transport tests pass. Reconstructed
streams from the eleven preserved old messages decode with zero submissions.
These are CPU-only protocol tests, not GPU or pool acceptance tests.


## Rig result (2026-10-24)

The bounded capture completed with 24 packets, zero kernel drops and ten decoded
messages. One existing-miner submit (id 866) had a unique matched response with
status=1 and result=true. Three outbound report_info requests were distinguished
from that submit. Both directions correctly report unverified initial boundaries.
See pool findings for the observed parameter shape and unresolved semantics.

## Capture a preceding notification and an accepted submission

Capture 04 is now transferred and both whole-file hashes match. Its accepted
submit precedes both captured notifies, leaving the accepted share's header
unavailable. Do not replay it or assign one of those later notifies to it.

The new `capture_share_context.py --captures DIRECTORY` uses the same three
stdlib transport modules. It watches the already running miner for up to 600
seconds/1,024 packets, stopping early on an accepted submit with preceding
notify candidates on the same TCP connection. It prints those candidates and
the submit/reply, rather than requiring screenshots of a base64 PCAP. It saves
all decoded records locally, so earlier candidate notifications are retained.
It does not assert that the latest preceding notify is the share's job.

The new decoder schema `pearlhash-decoded-capture-2` adds packet/time/stream-line
metadata and sorts records in capture completion order. The old statement that
records are grouped by direction is superseded. Duplicate request ids remain
ambiguous; a response before the request is not selected as its verdict.

22 CPU tests cover transport/login, capture parsing, chronological correlation,
header conversion/schema and context selection. These include late TCP gap
fills, retransmissions, sequence wrap, nanosecond timestamps, a response preceding
its request, notification/token confusion and actively written PCAP snapshots.
These changes neither run a GPU test nor establish custom-miner acceptance.
