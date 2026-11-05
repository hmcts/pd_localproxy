#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Record pilot HTTP responses and compare them without masking body differences.

Freeze upstream data/database/time and use two isolated database copies for POST
comparisons. Capture files may contain court data; they are created mode 0600.
"""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HEADERS = ['content-type','content-length','location','cache-control','expires','pragma']


def record(args):
    with io.open(args.cases,encoding='utf-8') as stream:
        cases=json.load(stream)
    captures=[]
    # Prevent redirects hiding a changed manager POST flow.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*unused,**kwargs): return None
    opener=urllib.request.build_opener(NoRedirect)
    for case in cases:
        request=urllib.request.Request(args.base.rstrip('/')+'/'+case['path'].lstrip('/'))
        if 'post' in case:
            request.data=urllib.parse.urlencode(case['post']).encode('utf-8')
            request.add_header('Content-Type','application/x-www-form-urlencoded')
        if args.auth_env:
            identity=os.environ[args.auth_env].encode('utf-8')
            request.add_header('Authorization','Basic '+base64.b64encode(identity).decode('ascii'))
        try:
            response=opener.open(request,timeout=args.timeout)
        except urllib.error.HTTPError as exc:
            response=exc
        with response:
            body=response.read()
            captures.append(dict(name=case['name'],path=case['path'],status=response.getcode(),
                headers=dict((name,response.headers.get(name)) for name in HEADERS),
                sha256=hashlib.sha256(body).hexdigest(),body=base64.b64encode(body).decode('ascii')))
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream: json.dump(captures,stream,sort_keys=True,indent=2)
    print('Recorded {0} responses into a private capture file.'.format(len(captures)))
    return 0


def compare(args):
    with io.open(args.before,encoding='utf-8') as stream: before=json.load(stream)
    with io.open(args.after,encoding='utf-8') as stream: after=json.load(stream)
    expected=dict((case['name'],case) for case in before)
    actual=dict((case['name'],case) for case in after)
    failures=[]
    for name in sorted(set(expected)|set(actual)):
        if name not in expected or name not in actual:
            failures.append(dict(name=name,difference='missing case'))
            continue
        for key in ['path','status','headers','body']:
            if expected[name][key] != actual[name][key]:
                failures.append(dict(name=name,difference=key))
    print(json.dumps(dict(matched=not failures,cases=len(expected),differences=failures),indent=2))
    return 1 if failures else 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command')
    capture=commands.add_parser('record')
    capture.add_argument('--base',required=True)
    capture.add_argument('--cases',required=True)
    capture.add_argument('--output',required=True)
    capture.add_argument('--auth-env',help='Environment variable containing operator:password; never stored in captures')
    capture.add_argument('--timeout',type=float,default=60)
    diff=commands.add_parser('compare')
    diff.add_argument('before')
    diff.add_argument('after')
    args=parser.parse_args()
    if not args.command: parser.error('Choose record or compare')
    return record(args) if args.command=='record' else compare(args)


if __name__=='__main__': sys.exit(main())
