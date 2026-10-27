#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only evidence for PHP removal. Run as root on each target after restart.

This inventory cannot certify an estate or detect a runtime concealed under an
arbitrary filename. Audit all applications, vhosts, containers, and custom runtimes.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys


def output(argv):
    process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    stdout,stderr=process.communicate()
    if process.returncode: raise RuntimeError('command failed')
    return stdout.decode('utf-8','replace')


def audit(args):
    findings=[]
    incomplete=[]
    try:
        modules=output([args.apache,'-M'])
        findings.extend('Apache module: '+line.strip() for line in modules.splitlines() if 'php' in line.lower())
    except (OSError,RuntimeError): incomplete.append('Apache loaded-module inventory')
    if shutil.which('rpm'):
        packages=output(['rpm','-qa','--qf','%{NAME} %{VERSION}-%{RELEASE}\n'])
    elif shutil.which('dpkg-query'):
        packages=output(['dpkg-query','-W','-f','${binary:Package} ${Version} ${db:Status-Status}\n'])
        packages='\n'.join(line for line in packages.splitlines() if line.endswith(' installed'))
    else:
        packages=''
        incomplete.append('RPM/DEB package inventory')
    findings.extend('Package: '+line for line in packages.splitlines() if re.search(r'(^|[-_])php',line,re.I))
    try:
        processes=output(['ps','-eo','pid=,comm='])
        for line in processes.splitlines():
            parts=line.strip().split(None,1)
            if len(parts)==2 and os.path.basename(parts[1]).lower().startswith('php'):
                findings.append('Process: '+line.strip())
    except (OSError,RuntimeError): incomplete.append('Process inventory')
    # Detect old mod_php mappings retained in workers after a graceful reload.
    if os.path.isdir('/proc'):
        for name in os.listdir('/proc'):
            if not name.isdigit(): continue
            try:
                with open('/proc/'+name+'/maps') as stream: mappings=stream.read()
                if re.search(r'/(?:lib)?php[^/\s]*\.so',mappings,re.I):
                    findings.append('PHP shared library still mapped in PID '+name)
            except IOError:
                if os.geteuid()!=0:
                    incomplete.append('Run as root to inspect process memory mappings')
                    break
    for name in ['php','php-cgi','php-fpm']:
        if shutil.which(name): findings.append('Executable on PATH: '+shutil.which(name))
    for root in args.scan_root:
        if not os.path.isdir(root):
            incomplete.append('Missing scan root: '+root)
            continue
        for parent,dirs,files in os.walk(root):
            for name in files:
                if re.search(r'\.(?:php\d?|phtml|phar|phps)$',name,re.I): findings.append('Legacy PHP source: '+os.path.join(parent,name))
                elif re.match(r'^(?:libphp.*\.so|php(?:-cgi|-fpm)?(?:[0-9.]+)?)$',name,re.I):
                    findings.append('Possible custom PHP runtime: '+os.path.join(parent,name))
    report=dict(findings=sorted(set(findings)),incomplete=sorted(set(incomplete)),
                scope='This host only; verify all network listeners, applications, vhosts and custom installations separately')
    print(json.dumps(report,indent=2))
    return 1 if findings or incomplete else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apache',default='/usr/sbin/httpd')
    parser.add_argument('--scan-root',action='append',required=True)
    sys.exit(audit(parser.parse_args()))
