#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline packaging, read-only preflight, and Apache cutover configuration.

Run with the target interpreter. No command installs a runtime, downloads packages,
changes a database, reloads Apache, or uninstalls PHP.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET

# Shared tools live in pd_localproxy/migration beside the sibling pd_cdu checkout.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
REPOS = {'localproxy': 'pd_localproxy', 'cdu': 'pd_cdu'}
ROUTES = {
    'localproxy': [('20-proxy', '/proxy/xhibit_proxy.php'),
                   ('21-checksum', '/software/checksum.php'),
                   ('22-download', '/software/download.php')],
    'cdu': [('30-content', '/xhibit_content.php'), ('40-screenshot', '/screenshot.php'),
            ('50-index', '/index.php')]}
MANAGER_ROUTES = [('60-manager-index', '/manager/index.php'),
                  ('61-manager-site', '/manager/site.php'),
                  ('62-manager-cdu', '/manager/cdu.php'),
                  ('63-manager-screenshot', '/manager/cduScreenshot.php')]


def write(path, data):
    with io.open(path, 'w', encoding='utf-8') as stream:
        stream.write(data)


def clean_absolute(path):
    if not os.path.isabs(path) or re.search(r'[\s"\x00-\x1f]', path):
        raise ValueError('Use an absolute path without whitespace or Apache metacharacters')
    return path


def package(args):
    interpreter = clean_absolute(args.python)
    repo = os.path.join(ROOT, REPOS[args.role])
    output = os.path.abspath(args.output)
    if os.path.exists(output):
        raise ValueError('Refusing to overwrite an existing package')
    # Explicit allowlist excludes PHP, INI credentials, SQL, tests, and legacy libraries.
    roots = ['python', 'cgi-bin']
    if args.role == 'localproxy':
        roots += ['proxy/xhibit.py']
        if args.with_manager:
            roots += ['manager/css', 'manager/fonts', 'manager/images']
    else:
        roots += ['css', 'images', 'xsl', 'jquery-3.1.1.min.js',
                  'display_documentNEW.js', 'onscreen-clock.js', 'localError.html',
                  'MODEL_COURT_PROVENANCE.json']
    manifest = {}
    with tarfile.open(output, 'w' if args.format == 'tar' else 'w:gz') as archive:
        for source in roots:
            path = os.path.join(repo, source)
            if os.path.islink(path):
                raise ValueError('Refusing to package symlink roots')
            files = []
            if os.path.isdir(path):
                for parent, directories, names in os.walk(path):
                    directories[:] = sorted(name for name in directories if name != '__pycache__')
                    if any(os.path.islink(os.path.join(parent, name)) for name in directories):
                        raise ValueError('Refusing to package symlink directories')
                    files.extend(os.path.join(parent, name) for name in sorted(names))
            else:
                files = [path]
            for filename in files:
                if os.path.islink(filename):
                    raise ValueError('Refusing to package symlinks')
                if not filename.lower().endswith(('.py','.cgi','.html','.css','.js','.png','.jpg',
                                                  '.gif','.svg','.woff','.woff2','.ttf','.eot','.xsl','.json')):
                    continue
                with open(filename,'rb') as stream:
                    data = stream.read()
                if b'<?php' in data.lower() or b'<?=' in data:
                    raise ValueError('PHP source found in allowlisted release file')
                relative = os.path.relpath(filename,repo).replace(os.sep,'/')
                if args.role == 'localproxy' and not args.with_manager and (
                        relative == 'python/manager.py' or relative.startswith('python/templates/')):
                    continue
                if relative == 'cgi-bin/xhibit.cgi':
                    data = ('#!' + interpreter + '\n').encode('utf-8') + data.split(b'\n',1)[1]
                entry = tarfile.TarInfo(relative)
                entry.size = len(data)
                entry.mode = 0o755 if relative.startswith('cgi-bin/') else 0o644
                entry.uid = entry.gid = 0
                entry.uname = entry.gname = 'root'
                archive.addfile(entry,io.BytesIO(data))
                manifest[relative] = hashlib.sha256(data).hexdigest()
        data = json.dumps(manifest,sort_keys=True,indent=2).encode('utf-8')
        entry = tarfile.TarInfo('MANIFEST.sha256.json')
        entry.size, entry.mode = len(data), 0o644
        archive.addfile(entry,io.BytesIO(data))
    print(json.dumps({'package':output,'files':len(manifest),'php_files':0},indent=2))


def apache(args):
    install = clean_absolute(args.install_root)
    config = clean_absolute(args.config)
    if not re.match(r'^/(?:[A-Za-z0-9_-]+/)*$', args.prefix):
        raise ValueError('Prefix must start/end with / and contain only path components')
    if args.role == 'localproxy' and args.with_manager and not args.auth_config:
        raise ValueError('--auth-config must point at the existing manager authentication directives')
    if args.auth_config:
        clean_absolute(args.auth_config)
    output = os.path.abspath(args.output)
    os.makedirs(output)  # Refuse to overwrite an existing cutover set.
    variable = 'XHIBIT_CONFIG' if args.role == 'localproxy' else 'XHIBIT_CDU_CONFIG'
    common = '''# Include inside the EXISTING VirtualHost; retain Listen, ACLs, TLS, and logging.
# Enable the OS mod_cgi (prefork) or mod_cgid module before using these fragments.
<Directory "{install}/cgi-bin">
    Options +ExecCGI -Indexes
    AllowOverride None
    AcceptPathInfo Off
    Require all granted
    SetEnv {variable} "{config}"
</Directory>
<Directory "{install}/python">
    Require all denied
</Directory>
<Directory "{install}/proxy">
    Require all denied
</Directory>
'''.format(install=install,variable=variable,config=config)
    if args.role == 'localproxy' and args.with_manager:
        common += '<Directory "{0}/cgi-bin">\n    SetEnv XHIBIT_WITH_MANAGER 1\n</Directory>\n'.format(install)
    static = (['manager/css','manager/fonts','manager/images'] if args.with_manager else []) if args.role == 'localproxy' else ['css','images','xsl']
    for path in static:
        common += 'Alias "{0}{1}/" "{2}/{1}/"\n'.format(args.prefix,path,install)
        common += '<Directory "{0}/{1}">\n    Options -Indexes\n    AllowOverride None\n    Require all granted\n</Directory>\n'.format(install,path)
    if args.role == 'cdu':
        for path in ['jquery-3.1.1.min.js','display_documentNEW.js','onscreen-clock.js','localError.html']:
            common += 'Alias "{0}{1}" "{2}/{1}"\n'.format(args.prefix,path,install)
            # These files live in the installation root, which Apache normally
            # denies. Grant only the exact public alias, not the whole code tree.
            public = re.escape(args.prefix + path)
            common += '<LocationMatch "^{0}$">\n    Require all granted\n</LocationMatch>\n'.format(public)
    write(os.path.join(output,'00-common.conf'),common)
    allowed = []
    routes = ROUTES[args.role] + (MANAGER_ROUTES if args.role == 'localproxy' and args.with_manager else [])
    for name,path in routes:
        public = args.prefix.rstrip('/') + path
        paths = [public]
        if path.endswith('/index.php'):
            paths.append(public[:-len('index.php')])
        allowed.extend(paths)
        fragment = '# Enable by renaming .conf.disabled to .conf; rollback by reversing that rename.\n'
        for url in paths:
            fragment += 'ScriptAliasMatch "^{0}$" "{1}/cgi-bin/xhibit.cgi"\n'.format(re.escape(url),install)
        if '/manager/' in public:
            fragment += '<LocationMatch "^(?:{0})$">\n    Include "{1}"\n</LocationMatch>\n'.format('|'.join(re.escape(url) for url in paths),args.auth_config)
        write(os.path.join(output,name+'.conf.disabled'),fragment)
    # Enable only AFTER all routes and all other host PHP consumers have been audited.
    final = '''# FINAL CUTOVER ONLY. Does not unload mod_php; remove LoadModule separately and restart Apache.
# This check applies to filesystem PHP; ScriptAlias targets end in .cgi and remain executable.
<FilesMatch "(?i)\\.(?:php[0-9]?|phtml|phar|phps)$">
    SetHandler None
    Require all denied
</FilesMatch>
'''
    # Deny unrecognised URL paths even when no physical file exists.
    exceptions = '|'.join(re.escape(url) for url in allowed)
    final += '<LocationMatch "^(?!(?:{0})$).*\\.php(?:/.*)?$">\n    Require all denied\n</LocationMatch>\n'.format(exceptions)
    write(os.path.join(output,'90-deny-legacy-php.conf.disabled'),final)
    print(json.dumps({'directory':output,'routes':allowed,'automatic_activation':False},indent=2))


def preflight(args):
    repo = os.path.abspath(args.install_root or os.path.join(ROOT,REPOS[args.role]))
    sys.path.insert(0,os.path.join(repo,'python'))
    from http_support import read_ini, command
    report = {'role':args.role,'python':sys.version.split()[0], 'executable':sys.executable,
              'failures':[], 'checks':[], 'warnings':[]}
    if sys.version_info < (3,4): report['failures'].append('Python 3.4 or later required')
    try:
        if args.role == 'cdu':
            # Read cdu.ini exactly as the CDU runtime does (parse_ini_file-style values).
            from cdu import read_settings
            values = read_settings(args.config)
        else:
            values = read_ini(args.config)
        mode = stat.S_IMODE(os.stat(args.config).st_mode)
        if mode & 0o007 or mode & 0o022:
            report['failures'].append('Config must not be world-readable or group/world-writable (use 0640)')
        if args.role == 'localproxy':
            # The legacy parser read these through ConfigParser interpolation ("%%" meant "%").
            # INI values are now read raw; never print the value itself.
            for key in ['DBConn','DBName','DBusername','DBpasswd']:
                if '%%' in values.get(key, ''):
                    report['failures'].append('Config ' + key + ' contains "%%": legacy parser read it as "%"; '
                                              'values are now raw, so confirm and write the real value')
            if args.with_manager:
                from manager import csrf_secret
                if csrf_secret(values) is None:
                    report['failures'].append('Manager requires managerCsrfSecret: a random value of at least '
                                              '32 bytes (see config/ops.ini.example); POSTs are refused without it')
            for name in ['pymysql','bs4']:
                module = __import__(name)
                report['checks'].append(name + '=' + getattr(module,'__version__','installed'))
            from database import Database
            db = Database.from_values(values)
            try: report['failures'].extend(db.validate_schema(with_manager=args.with_manager))
            finally: db.close()
            if not values.get('cduArchive') or not os.path.isabs(values['cduArchive']):
                report['failures'].append('Absolute cduArchive configuration required')
            elif not os.path.isfile(values['cduArchive']):
                report['failures'].append('Configured Python-only cdu.tar is missing')
            else:
                with tarfile.open(values['cduArchive'], 'r:') as bundle:
                    entries = bundle.getmembers()
                    if any(not entry.isfile() or entry.name.lower().endswith(('.php','.php3','.php4','.php5','.php7','.php8','.phtml','.phar','.phps','.ini','.zip','.tar','.gz'))
                           or entry.name.startswith('/') or '..' in entry.name.split('/') for entry in entries):
                        report['failures'].append('Unsafe/legacy content in configured cdu.tar')
                    if any(b'<?php' in bundle.extractfile(entry).read().lower() or
                           b'<?=' in bundle.extractfile(entry).read() for entry in entries if entry.isfile()):
                        report['failures'].append('PHP source embedded in configured cdu.tar')
                    if 'python/cdu.py' not in [entry.name for entry in entries]:
                        report['failures'].append('Configured cdu.tar is not the Python distribution')
            if args.with_manager and (not args.auth_config or not os.path.isfile(args.auth_config)):
                report['failures'].append('Existing manager Apache authentication include required')
            elif args.with_manager:
                with io.open(args.auth_config,encoding='utf-8') as stream:
                    authorization=stream.read()
                if not re.search(r'^\s*Require\s+',authorization,re.M):
                    report['failures'].append('Manager include must contain the original Require authorization directives')
            report['checks'].append('Audit page.php / selector.php and every other PHP consumer before disabling PHP')
        else:
            executable = values.get('xsltproc','/usr/bin/xsltproc')
            report['checks'].append(command([executable,'--version']).decode('utf-8','replace').strip())
            from cdu import FULL
            for name in sorted(set(list(FULL.values()) + ['xml2json'])):
                path = os.path.join(repo,'xsl','new',name+'.xsl')
                try: ET.parse(path)
                except (IOError,ET.ParseError): report['failures'].append('Invalid/missing stylesheet: new/'+name+'.xsl')
            for key in ['fetch', 'timeout', 'macAddressCmd']:
                if not values.get(key): report['failures'].append('Missing Model Court config key: '+key)
            # timeout is required above; the others default to 60 seconds in cdu.py.
            for key in ['timeout','transformTimeout','macCommandTimeout','screenshotTimeout']:
                if key in values:
                    try: number = float(values[key])
                    except ValueError: number = None
                    if number is None or not 0 < number < float('inf'):
                        report['failures'].append('Config ' + key + ' must be a positive number of seconds')
            if 'defaultMacAddress' in values:
                report['warnings'].append('defaultMacAddress is ignored: empty macAddressCmd output requests 00:00:00:00:00:00')
            report['checks'].append('macAddressCmd is not run by preflight: confirm it prints this CDU\'s MAC as the Apache account')
            for key in ['lastUpdatedLocation','timestampMonitorFile']:
                path = values[key]
                writable = os.access(path,os.W_OK) if os.path.exists(path) else os.access(os.path.dirname(path),os.W_OK)
                if not writable:
                    report['failures'].append('Apache account cannot update state file: ' + path)
            sudo = values.get('sudo','/usr/bin/sudo')
            helper = values.get('captureHelper','/usr/local/libexec/xhibit-capture')
            if not os.path.isfile(helper) or not os.access(helper,os.X_OK):
                report['failures'].append('Missing or non-executable captureHelper: ' + helper)
            # List (do not run) the exact screenshot command the CDU uses, as the invoking account.
            try:
                command([sudo,'-n','-l','-u','xhibit',helper,'0'*32+'-www-data'],timeout=15)
                report['checks'].append('sudo -n rule for captureHelper as xhibit is available to this account')
            except (OSError,RuntimeError,subprocess.TimeoutExpired):
                report['failures'].append('sudo -n rule for captureHelper as xhibit is not available to this account')
            report['checks'].append('Run CDU preflight as the Apache account; verify screenshot capture during the pilot')
    except Exception as exc:
        # Never print exception text: connection/configuration errors can contain credentials.
        report['failures'].append('Prerequisite check failed: ' + type(exc).__name__)
    print(json.dumps(report,sort_keys=True,indent=2))
    return 1 if report['failures'] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command')
    pack = commands.add_parser('package')
    pack.add_argument('role',choices=sorted(REPOS))
    pack.add_argument('--python',required=True)
    pack.add_argument('--output',required=True)
    pack.add_argument('--format',choices=['tar.gz','tar'],default='tar.gz')
    conf = commands.add_parser('apache')
    conf.add_argument('role',choices=sorted(REPOS))
    conf.add_argument('--install-root',required=True)
    conf.add_argument('--config',required=True)
    conf.add_argument('--auth-config')
    conf.add_argument('--prefix',default='/')
    conf.add_argument('--output',required=True)
    check = commands.add_parser('preflight')
    check.add_argument('role',choices=sorted(REPOS))
    check.add_argument('--install-root')
    check.add_argument('--config',required=True)
    check.add_argument('--auth-config')
    for command_parser in (pack, conf, check):
        command_parser.add_argument('--with-manager',action='store_true',
                                    help='Include optional, not production-verified manager (default off)')
    args = parser.parse_args()
    if args.command is None: parser.error('Choose package, apache, or preflight')
    if args.role == 'cdu' and args.with_manager:
        parser.error('--with-manager applies only to localproxy')
    try:
        return {'package':package,'apache':apache,'preflight':preflight}[args.command](args) or 0
    except (ValueError,OSError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    sys.exit(main())
