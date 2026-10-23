# Observed Pearlhash traffic — 2026-10-23

These are capture observations, not a decoded protocol specification.
No field meanings, cipher, key derivation, share encoding or target semantics
have been inferred as implementation requirements.

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
