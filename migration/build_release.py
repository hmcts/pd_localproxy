#!/usr/bin/env python3
"""Build a NEW local release directory. No deployment, network or host changes."""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(HERE))


def build(output, proxy_python, cdu_python, with_manager=False):
    os.makedirs(output)
    revisions = {}
    for name in ('pd_localproxy', 'pd_cdu'):
        repo = os.path.join(WORKSPACE, name)
        def git(*arguments):
            return subprocess.check_output(['git', '-C', repo] + list(arguments)).decode('utf-8').strip()
        revisions[name] = {'commit': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'),
                           'dirty_worktree': bool(git('status', '--porcelain'))}
    with io.open(os.path.join(output, 'RELEASE.json'), 'w', encoding='utf-8') as stream:
        json.dump({'sources': revisions, 'manager_default': False, 'optional_manager_built': with_manager,
                   'production_activation': False}, stream, sort_keys=True, indent=2)
    deploy = os.path.join(HERE, 'deploy.py')
    def run(*args):
        subprocess.check_call([sys.executable, deploy] + list(args))
    for role, interpreter in [('localproxy', proxy_python), ('cdu', cdu_python)]:
        run('package', role, '--python', interpreter, '--output', os.path.join(output, role+'-python.tar.gz'))
        run('apache', role, '--install-root', '/opt/xhibit/'+role, '--config',
            '/etc/xhibit/'+('ops' if role == 'localproxy' else 'cdu')+'.ini',
            '--output', os.path.join(output, role+'-apache'))
    run('package', 'cdu', '--python', cdu_python, '--format', 'tar', '--output', os.path.join(output, 'cdu.tar'))
    if with_manager:
        run('package', 'localproxy', '--python', proxy_python, '--with-manager',
            '--output', os.path.join(output, 'localproxy-python-with-manager.tar.gz'))
        run('apache', 'localproxy', '--install-root', '/opt/xhibit/localproxy', '--config', '/etc/xhibit/ops.ini',
            '--with-manager', '--auth-config', '/etc/xhibit/manager-auth.conf',
            '--output', os.path.join(output, 'optional-manager-apache'))
    paths = ['deploy.py', 'verify_release.py', 'audit_php.py', 'compare_http.py', 'collect_production.py', 'collect_schema.sh',
             'compare_github.py', 'Compare-XhibitGitHub.ps1', 'xhibit-capture', 'sudoers-cdu.example',
             'README.md', 'VALIDATION.md', 'MODEL_COURT_PROVENANCE.json', 'COMPARE_GITHUB.md', 'COLLECT_PRODUCTION.md',
             'cases-cdu.example.json', 'cases-localproxy.example.json']
    sources = [(os.path.join(HERE, name), 'migration/'+name) for name in paths]
    sources.extend([(os.path.join(WORKSPACE, 'pd_localproxy', 'config', 'ops.ini.example'), 'config/ops.ini.example'),
                    (os.path.join(WORKSPACE, 'pd_cdu', 'config', 'cdu.ini.example'), 'config/cdu.ini.example')])
    manifest = {}
    with tarfile.open(os.path.join(output, 'migration-tools.tar.gz'), 'w:gz') as archive:
        for source, name in sources:
            with open(source, 'rb') as stream: data = stream.read()
            entry = tarfile.TarInfo(name)
            entry.mode = 0o755 if name.endswith(('.py', '.sh')) or name.endswith('/xhibit-capture') else 0o644
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
            manifest[name] = hashlib.sha256(data).hexdigest()
        data = json.dumps(manifest, sort_keys=True, indent=2).encode('utf-8')
        entry = tarfile.TarInfo('MANIFEST.sha256.json')
        entry.mode, entry.size = 0o644, len(data)
        archive.addfile(entry, io.BytesIO(data))
    lines = []
    for parent, directories, names in os.walk(output):
        for name in sorted(names):
            path = os.path.join(parent, name)
            with open(path, 'rb') as stream: digest = hashlib.sha256(stream.read()).hexdigest()
            lines.append(digest+'  '+os.path.relpath(path, output).replace(os.sep, '/'))
    with io.open(os.path.join(output, 'SHA256SUMS'), 'w', encoding='utf-8') as stream:
        stream.write('\n'.join(sorted(lines))+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--proxy-python', required=True)
    parser.add_argument('--cdu-python', required=True)
    parser.add_argument('--with-manager', action='store_true')
    args = parser.parse_args()
    build(os.path.abspath(args.output), args.proxy_python, args.cdu_python, args.with_manager)
