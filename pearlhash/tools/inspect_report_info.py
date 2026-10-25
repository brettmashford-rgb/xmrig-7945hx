#!/usr/bin/env python3
"""Inspect saved report_info schema; no new capture, network or GPU work. ISC.

String values are redacted except bounded numeric strings; nested JSON strings
are described recursively. Login/submit/notify bodies are never printed.
"""
import argparse
import json
import math
from pathlib import Path
import re

MAX_FILE=32*1024**2
NUMERIC=re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z')
SENSITIVE={'wallet','user','username','password','pass','worker','worker_id','worker_nonce',
           'miner_nonce','nonce','token','session','session_id','address','login','private_key','key'}
SAFE_KEY=re.compile(r'(?:[A-Za-z_][A-Za-z0-9_.-]{0,63}|[0-9]{1,4})\Z')


def describe(value,depth=0):
    if depth>6:return {'type':type(value).__name__,'depth_limit':True}
    if value is None or type(value)is bool:return value
    if type(value)in(int,float):
        return value if type(value)is int or math.isfinite(value)else{'type':'nonfinite-number'}
    if isinstance(value,str):
        if len(value)<=32 and NUMERIC.fullmatch(value):return {'type':'numeric-string','value':value}
        if len(value)<=65536 and value.lstrip().startswith(('{','[')):
            try:parsed=json.loads(value)
            except(ValueError,RecursionError):pass
            else:return {'type':'json-string','value':describe(parsed,depth+1)}
        return {'type':'string','characters':len(value),'redacted':True}
    if isinstance(value,list):
        if len(value)>32:return {'type':'array','length':len(value),'first':describe(value[0],depth+1)}
        return [describe(v,depth+1)for v in value]
    if isinstance(value,dict):
        result={}
        for index,(key,item)in enumerate(list(value.items())[:32]):
            label=key if isinstance(key,str)and SAFE_KEY.fullmatch(key)else f'<key-{index}-redacted>'
            result[label]=({'type':type(item).__name__,'redacted':True}
                           if isinstance(key,str)and key.lower()in SENSITIVE else describe(item,depth+1))
        if len(value)>32:result['<total-fields>']=len(value)
        return result
    return {'type':type(value).__name__}


def report_records(document):
    if not isinstance(document,dict)or document.get('schema')!='pearlhash-decoded-capture-1':return []
    records=document.get('records')
    if not isinstance(records,list)or len(records)>100000:return []
    return [r for r in records if isinstance(r,dict)and r.get('direction')=='out'
            and isinstance(r.get('json'),dict)and r['json'].get('method')=='report_info']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures',type=Path,required=True)
    args=parser.parse_args()
    files=sorted(args.captures.glob('*.decoded.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True)
    for path in files[:64]:
        if not path.is_file()or path.stat().st_size>MAX_FILE:continue
        document=json.loads(path.read_text());reports=report_records(document)
        if not reports:continue
        print('Saved decoded capture found; no new capture required.',flush=True)
        print('Captured report_info requests:',len(reports),flush=True)
        for index,record in enumerate(reports[:3],1):
            request=record['json']
            print('REPORT_INFO_PARAMS',index,':',json.dumps(describe(request.get('params')),separators=(',',':')),flush=True)
            request_id=request.get('id');connection=record.get('connection')
            replies=[r['json']for r in document['records']if isinstance(r,dict)
                     and r.get('direction')=='in'and r.get('connection')==connection
                     and isinstance(r.get('json'),dict)and type(r['json'].get('id'))is type(request_id)
                     and r['json'].get('id')==request_id]
            requests=[r for r in document['records']if isinstance(r,dict)
                      and r.get('direction')=='out'and r.get('connection')==connection
                      and isinstance(r.get('json'),dict)and type(r['json'].get('id'))is type(request_id)
                      and r['json'].get('id')==request_id]
            if len(replies)==1 and len(requests)==1:
                reply=replies[0]
                print('MATCHED_REPORT_RESPONSE:',json.dumps({'status':describe(reply.get('status')),
                    'result':describe(reply.get('result'))},separators=(',',':')),flush=True)
            else:print('MATCHED_REPORT_RESPONSE: unavailable or ambiguous',flush=True)
        print('Inspection complete. No network, GPU work, submitted share or miner change.',flush=True)
        return 0
    raise ValueError('no saved decoded report_info messages found')


if __name__=='__main__':
    try:raise SystemExit(main())
    except(OSError,ValueError,TypeError,KeyError,RecursionError)as exc:
        print('STOP:',exc,flush=True);raise SystemExit(1)
