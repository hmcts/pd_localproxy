#!/usr/bin/env python3
"""Read-only local artifact audit, not host-level PHP-removal certification."""
import argparse
import hashlib
import io
import json
import os
import re
import tarfile


def safe(name):
    return (bool(name) and not name.startswith('/') and '\\' not in name and
            not any(part in ('', '.', '..') for part in name.split('/')))


def verify(output):
    with io.open(os.path.join(output, 'SHA256SUMS'), encoding='utf-8') as stream:
        for line in stream:
            expected, name = line.rstrip('\n').split('  ', 1)
            if not safe(name) or os.path.islink(os.path.join(output, name)):
                raise ValueError('Unsafe checksum path')
            with open(os.path.join(output, name), 'rb') as source:
                if hashlib.sha256(source.read()).hexdigest() != expected:
                    raise ValueError('Release checksum mismatch: '+name)
    report, contents = {}, {}
    for name in ('localproxy-python.tar.gz', 'cdu-python.tar.gz', 'cdu.tar',
                 'localproxy-python-with-manager.tar.gz', 'migration-tools.tar.gz'):
        path = os.path.join(output, name)
        if not os.path.exists(path) and name == 'localproxy-python-with-manager.tar.gz':
            continue
        with tarfile.open(path, 'r:' if name == 'cdu.tar' else 'r:gz') as archive:
            data = {}
            for member in archive:
                if not safe(member.name) or not member.isfile() or member.name in data:
                    raise ValueError('Unsafe/nonregular/duplicate archive member')
                if member.uid or member.gid or member.mode not in (0o644, 0o755):
                    raise ValueError('Archive permissions/ownership are not normalized')
                body = archive.extractfile(member).read()
                if re.search(r'(?i)\.(?:php[0-9]?|phtml|phar|phps|zip|tar|gz)$', member.name):
                    raise ValueError('PHP/nested archive in release')
                if name != 'migration-tools.tar.gz' and (b'<?php' in body.lower() or b'<?=' in body):
                    raise ValueError('Embedded PHP source in application artifact')
                data[member.name] = body
            manifest = json.loads(data.pop('MANIFEST.sha256.json').decode('utf-8'))
            if set(manifest) != set(data):
                raise ValueError('Manifest file set mismatch')
            for filename, expected in manifest.items():
                if hashlib.sha256(data[filename]).hexdigest() != expected:
                    raise ValueError('Manifest digest mismatch')
            if name == 'localproxy-python.tar.gz' and any('manager' in filename or filename.endswith('.ini') for filename in data):
                raise ValueError('Default localproxy package contains optional manager/private config')
            if name.startswith('cdu') and any(filename.endswith('.ini') for filename in data):
                raise ValueError('CDU package contains private config')
            contents[name] = data
            report[name] = {'files':len(data), 'manifest_verified':True, 'php_files':0}
    if contents['cdu.tar'] != contents['cdu-python.tar.gz']:
        raise ValueError('CDU compressed/uncompressed payloads differ')
    with io.open(os.path.join(output, 'RELEASE.json'), encoding='utf-8') as stream:
        release = json.load(stream)
    if any(source['dirty_worktree'] for source in release['sources'].values()):
        raise ValueError('Release was built from uncommitted work')
    print(json.dumps({'artifacts':report, 'sources':release['sources'], 'host_remediation_certified':False}, sort_keys=True, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    verify(parser.parse_args().directory)
