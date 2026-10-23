#!/usr/bin/env python3
"""Independent Pearlhash transport + bounded login-only probe. ISC license.

No GPU, mining, share submission, reconnect loop, or service management.
Only the captured outer transport and login schema are implemented.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import time

COEFFICIENTS = (
    30, 98, 196, 144, 155, 170, 71, 39, 58, 150, 80, 173,
    71, 27, 97, 172, 99, 54, 12, 60, 89, 14, 72, 89,
    34, 69, 189, 187, 42, 5, 1, 4, 8, 3, 2, 99,
    232, 30, 244, 6, 9, 4, 11, 171, 55, 99, 102, 123,
)
MAX_LINE = 65536
AGENT = "pearlhash-dev/0.0.6-probe"


def transform(body, nonce):
    """Symmetric byte mask; this is obfuscation, not encryption/authentication."""
    if not 0 <= nonce <= 0xffffffff:
        raise ValueError("nonce outside u32")
    mask = bytes((nonce * p - nonce % p) & 255 for p in COEFFICIENTS)
    return bytes(value ^ mask[i % 48] for i, value in enumerate(body))


def encode(message, nonce=None):
    if nonce is None:
        nonce = 10 + secrets.randbelow(0xfffffff5)  # 10..fffffffe
    if not 10 <= nonce <= 0xfffffffe:
        raise ValueError("unsupported encoder nonce")
    body = json.dumps(message, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")
    line = (nonce.to_bytes(4, "big") + transform(body, nonce)).hex().encode("ascii") + b"\n"
    if len(line) > MAX_LINE:
        raise ValueError("frame exceeds size limit")
    return line


def decode(line, *, max_line=MAX_LINE):
    if type(max_line) is not int or not 1 <= max_line <= 8 * 1024 * 1024:
        raise ValueError("invalid decoder size limit")
    if not isinstance(line, bytes) or not line.endswith(b"\n"):
        raise ValueError("frame must end in LF")
    body = line[:-1]
    if len(line) > max_line or len(body) < 10 or len(body) % 2:
        raise ValueError("invalid frame length")
    if any(c not in b"0123456789abcdefABCDEF" for c in body):
        raise ValueError("frame is not strict ASCII hex")
    raw = bytes.fromhex(body.decode("ascii"))
    plain = transform(raw[4:], int.from_bytes(raw[:4], "big"))
    def reject_constant(value):
        raise ValueError("non-finite JSON number")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result
    message = json.loads(plain.decode("utf-8"), parse_constant=reject_constant,
                         object_pairs_hook=unique_object)
    if not isinstance(message, dict):
        raise ValueError("expected JSON object")
    return message


def summarize(message):
    if message.get("id") == 0:
        accepted = message.get("status") == 1 and message.get("result") is True
        return "LOGIN: " + ("accepted (not a share verdict)" if accepted else "not accepted")
    result = message.get("result")
    if isinstance(result, list) and result:
        if result[0] == "extranonce":
            value = result[1] if len(result) > 1 else None
            return "EXTRANONCE: received; characters=" + str(len(value) if isinstance(value, str) else "invalid")
        if result[0] == "notify":
            lengths = [len(x) if isinstance(x, str) else type(x).__name__ for x in result[1:]]
            return "NOTIFY: received; field lengths=" + json.dumps(lengths) + "; inner payload unresolved"
    return "OTHER: decoded JSON object (retained locally)"


def probe(host, port, wallet, worker, output, seconds=30, connect=socket.create_connection):
    if not 1 <= seconds <= 60:
        raise ValueError("duration must be 1..60 seconds")
    login = {"id": 0, "method": "login", "params": [wallet, worker, AGENT]}
    records = [{"direction": "out", "json": login}]
    accepted = extra = notify = False
    # Reserve output before making any connection. Never overwrite earlier captures.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    error = None
    started = time.monotonic()
    try:
        with connect((host, port), timeout=min(10, seconds)) as stream:
            stream.sendall(encode(login))
            pending = b""
            for _ in range(16):
                while b"\n" not in pending:
                    remaining = seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        raise TimeoutError("probe deadline reached")
                    stream.settimeout(remaining)
                    chunk = stream.recv(min(4096, MAX_LINE + 1 - len(pending)))
                    if not chunk:
                        raise ConnectionError("pool closed before all expected messages")
                    pending += chunk
                    if len(pending.split(b"\n", 1)[0]) >= MAX_LINE:
                        raise ValueError("oversized pool frame")
                line, pending = pending.split(b"\n", 1)
                message = decode(line + b"\n")
                records.append({"direction": "in", "json": message})
                print(summarize(message), flush=True)
                if message.get("id") == 0:
                    accepted = message.get("status") == 1 and message.get("result") is True
                    if not accepted:
                        raise ValueError("pool did not accept diagnostic login")
                result = message.get("result")
                if isinstance(result, list) and result:
                    extra |= result[0] == "extranonce"
                    notify |= result[0] == "notify"
                if accepted and extra and notify:
                    break
            if not (accepted and extra and notify):
                raise ValueError("message limit reached before complete diagnostic exchange")
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        error = type(exc).__name__ + ": " + str(exc)
    finally:
        document = {"schema": "pearlhash-login-probe-1", "endpoint": [host, port],
                    "agent": AGENT, "records": records, "error": error,
                    "submitted_shares": 0}
        with os.fdopen(fd, "w") as destination:
            json.dump(document, destination, indent=2, allow_nan=False)
            destination.write("\n")
    print("Local transcript:", output)
    print("No shares submitted; no GPU work; no service or clock changes.")
    if error:
        print("STOP:", error)
        return 1
    print("PASS: independent login and outer decoding; not mining or pool share acceptance.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--worker", default="5060-dev-probe")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.wallet or len(args.wallet) > 256 or not args.worker or len(args.worker) > 64:
        parser.error("invalid wallet/worker length")
    return probe("pool.pearlhash.xyz", 9000, args.wallet, args.worker, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
