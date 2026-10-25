#!/usr/bin/env python3
"""Bind saved pool messages to explicit job configuration/state. ISC.

Reads existing local captures only. No pool connection, GPU/proof rebuild or
share submission. Saved login success is not a mining/share acceptance verdict.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
from pool.job import Notify
from pool.session import MiningProfile, PoolSession
from reference.native_hash import small_hash
from reference.patterns import PeriodicPattern


def read_object(path, cap=8*1024**2):
    if path.stat().st_size > cap:
        raise ValueError('local JSON input exceeds size cap')
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('expected local JSON object')
    return raw, value


def check_saved(context_path, replay_path, login_path):
    _, replay = read_object(replay_path, 1024**2)
    if replay.get('gpu_math_checked') is not True or replay.get('official_cpu_verifier') != 'passed':
        raise ValueError('existing captured-share replay completion is missing')
    raw, context = read_object(context_path)
    if hashlib.sha256(raw.removesuffix(b'\n')).hexdigest() != replay.get('private_context_sha256'):
        raise ValueError('local context differs from completed replay')
    selected = [c for c in context['contexts'] if c['submit'].get('id') == replay['selected_submit_id']]
    if len(selected) != 1:
        raise ValueError('expected unique captured replay context')
    selected = selected[0]
    params = selected['submit']['params'][0]
    if params.get('sb') != 1 or params.get('tail_mode') != 1 or params.get('sb_p') != []:
        raise ValueError('unsupported explicit constant-signal profile')
    config = bytes.fromhex(replay['facts']['config'])
    if len(config) != 52 or config[20:] != bytes(32):
        raise ValueError('unsupported dense configuration encoding')
    k, rank, mma = struct.unpack_from('<IHH', config)
    if mma != 0:
        raise ValueError('unsupported integer MMA configuration')
    profile = MiningProfile(params['m'], params['n'], k, rank,
                            PeriodicPattern(config[8:14]), PeriodicPattern(config[14:20]))
    if (profile.config != config or params['k'] != k or params['rank'] != rank
            or params['tile_h'] != profile.rows.size or params['tile_w'] != profile.cols.size):
        raise ValueError('captured submit/profile configuration differs')
    records = [r for r in context['records'] if r.get('direction') == 'in'
               and r.get('connection') == selected['connection']
               and r.get('packet') == replay['selected_notify_packet']]
    if len(records) != 1:
        raise ValueError('expected unique verified replay notification')
    notify = Notify.parse(records[0]['json'])
    if notify.version_marker != '3':
        raise ValueError('saved replay is outside explicit V3 policy')
    if (small_hash(notify.header+profile.config).hex() != replay['facts']['job_key']
            or profile.share_bound(notify.target_bytes).to_bytes(32, 'little').hex()
            != replay['facts']['bound_le']):
        raise ValueError('pool header/config job key or scaled target differs from verified replay')
    print('PASS: explicit profile + decoded pool header reproduce the verified replay job key and share bound', flush=True)
    print('No matrix hashes, GPU math or proof verification repeated.', flush=True)

    # This independent login is a separate session, never combined with the
    # captured miner's nonce/session identity. Inspect field order/state only.
    _, login = read_object(login_path)
    if login.get('error') is not None:
        raise ValueError('saved independent login probe recorded an error')
    session = PoolSession(profile, cert_version=3)
    latest_notify = None
    incoming = 0
    for record in login['records']:
        if record.get('direction') != 'in':
            continue
        message = record['json']
        session.consume(message)
        incoming += 1
        result = message.get('result')
        if isinstance(result, list) and result and result[0] == 'notify':
            latest_notify = message
    job = session.snapshot()
    if not session.is_current(job) or latest_notify is None:
        raise ValueError('saved independent exchange did not produce a ready job snapshot')
    if len(job.assigned_extranonce) != 8 or len(job.opaque_metadata) != 124:
        raise ValueError('saved assigned nonce/metadata widths differ')
    print(f'PASS: saved independent login/extranonce/notify exchange builds a gated job snapshot ({incoming} messages)', flush=True)

    replacement = copy.deepcopy(latest_notify)
    target = int.from_bytes(job.target_bytes, 'little')
    changed_target = target//2 if target > 1 else 2
    replacement['result'][2] = changed_target.to_bytes(32, 'little').hex()
    changed = session.consume(replacement)
    if (session.is_current(job) or not session.is_current(changed)
            or changed.generation <= job.generation or changed.job_key != job.job_key
            or changed.share_bound != profile.share_bound(changed.target_bytes)):
        raise ValueError('target replacement did not invalidate/rebind job state')
    session.reset()
    if session.snapshot() is not None or session.is_current(changed):
        raise ValueError('connection reset retained stale work')
    print('PASS: controlled target replacement and connection reset invalidate stale job handles', flush=True)
    print('V3 is explicitly configured. Metadata/token meanings and extranonce-to-worker mapping remain unproven.', flush=True)
    return {'complete': True, 'cpu_job_binding_checked': True, 'scaled_share_target_checked': True,
            'saved_login_state_checked': True, 'generation_replacement_reset_checked': True,
            'gpu_executed': False, 'proof_verifier_executed': False,
            'live_pool_connection': False, 'submitted_shares': 0,
            'extranonce_worker_role_verified': False, 'opaque_metadata_interpretation_verified': False,
            'scope': 'saved message/job-state binding only; no live worker or pool verdict'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--replay-manifest', type=Path, required=True)
    parser.add_argument('--login', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or not args.report.parent.is_dir():
        raise ValueError('report already exists or parent directory is missing')
    report = check_saved(args.context, args.replay_manifest, args.login)
    with args.report.open('x') as output:
        json.dump(report, output, indent=2)
        output.write('\n')
    print('Completion saved. No connection, GPU work, submitted share or miner change.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        print('STOP:', error, flush=True)
        raise SystemExit(1)
