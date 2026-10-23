#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect private, best-effort-redacted production evidence without deploying.

Python 3.4+, standard library only. Reads application/configuration files and
local system metadata. Writes ONLY a new private evidence directory and archive.
Never executes collected application files, queries a database, requests a web
page, scans the network, installs packages or changes/restarts a service.
Automatic redaction is NOT a guarantee: review the bundle before sharing.
"""
import sys
if sys.version_info < (3, 4):
    sys.exit('Python 3.4+ required; nothing has been installed or upgraded.')
import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import tarfile
import tempfile

TEXT_EXTENSIONS = ('.php', '.py', '.cgi', '.xsl', '.xslt', '.js', '.css',
                   '.sh', '.bash', '.ini', '.conf', '.properties', '.desktop')
SCHEDULER_ROOTS = ['/etc/cron.d', '/etc/cron.daily', '/etc/cron.hourly',
                   '/var/spool/cron', '/var/spool/cron/crontabs']
SCHEDULER_FILES = ['/etc/crontab']
EXCLUDED_DIRS = set(['.git', '.svn', '__pycache__', 'logs', 'log', 'cache',
    'tmp', 'temp', 'testdata', 'test-data', 'uploads', 'upload', 'screenshots',
    'captures', 'sessions', 'node_modules', '.ssh', 'private'])
PRIVATE_NAMES = re.compile(r'(?i)(?:^\.env(?:\.|$)|^\.(?:htpasswd|netrc)$|passwd|password|shadow|'
                           r'private.key|id_rsa|id_ed25519|\.pem$|\.key$|\.p12$|'
                           r'\.pfx$|\.jks$|keystore|tomcat-users\.xml|\.xauthority)')
SECRET = r'(?:[\w.-]*(?:passwd|password|pwd|secret|token|credential|api[_-]?key)[\w.-]*|DBusername|dbuser)'
COMMON_CONFIG = ['/etc/os-release', '/etc/httpd/conf/httpd.conf',
    '/etc/httpd/conf/localproxy.conf', '/etc/apache2/apache2.conf',
    '/etc/apache2/ports.conf', '/etc/sudoers', '/etc/sysconfig/httpd',
    '/home/xhibit/.xinitrc', '/home/xhibit/.xsession',
    '/home/xhibit/.config/lxsession/LXDE-pi/autostart',
    '/opt/moj/tomcat/conf/server.xml', '/opt/moj/tomcat/conf/context.xml']
CONFIG_ROOTS = ['/etc/httpd/conf.d', '/etc/httpd/conf.modules.d',
    '/etc/apache2/sites-available', '/etc/apache2/sites-enabled',
    '/etc/apache2/conf-available', '/etc/apache2/conf-enabled',
    '/etc/apache2/mods-available', '/etc/apache2/mods-enabled', '/etc/sudoers.d',
    '/home/xhibit/.config/autostart']
ROOTS = {
    'proxy': ['/var/www/court-display/proxy', '/var/www/court-display/proxycode',
              '/var/www/cgi-bin/xhibit.py', '/var/www/lan/manager', '/var/www/lan/cdu',
              '/var/www/lan/xhibit', '/var/www/court-display/software',
              '/home/xhibit/Checksum/checksum.php', '/home/xhibit/bin',
              '/opt/updatechecksums'],
    'cdu': ['/var/www/lan/cdu', '/var/www/cdu', '/var/www/html', '/home/xhibit/bin']}


def redact(text):
    """Redact common credential patterns; preserve non-secret paths/directives."""
    patterns = [
        (r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', '[REDACTED PRIVATE KEY]', re.S),
        (r'(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+(?::[^\s/@]*)?@', r'\1[REDACTED]@', 0),
        (r'(?im)^(\s*' + SECRET + r'\s*[=:]\s*).*$' , r'\1[REDACTED]', 0),
        (r'(?i)((?:[\w$]+[.\[\]"\x27]*)?' + SECRET + r'[\]"\x27]*\s*(?:=>|=|:)\s*)(["\x27])[^\r\n]*?\2',
         r'\1\2[REDACTED]\2', 0),
        (r'(?i)(\b(?:password|passwd|pwd|user(?:name)?)\s*=\s*)([^;\s&"\x27<>]+)', r'\1[REDACTED]', 0),
        # Tomcat server.xml/context.xml: keystorePass, truststorePass, keyPass, username="...".
        (r'(?i)(\b[\w.-]*(?:pass|user(?:name)?)\s*=\s*)(["\x27])[^\r\n]*?\2', r'\1\2[REDACTED]\2', 0),
        (r'(?im)^(\s*[\w.-]*pass\s*[=:]\s*).*$' , r'\1[REDACTED]', 0),
        (r'(?im)^([ \t]*(?:SetEnv|SetEnvIf)\s+' + SECRET + r'\s+).*$' , r'\1[REDACTED]', 0),
        (r'(?im)^([ \t]*AuthLDAPBindPassword\s+).*$' , r'\1[REDACTED]', 0),
        (r'(?i)(Authorization[\s:"\x27=]+(?:Basic|Bearer)\s+)[^\s"\x27<>]+', r'\1[REDACTED]', 0),
        (r'(?i)(\b(?:password|passwd|secret|token)\s*=\s*)(["\x27])[^\r\n]*?\2', r'\1\2[REDACTED]\2', 0),
        (r'(?i)(<(?:password|passwd|secret|token)>)[^<]*(</[^>]+>)', r'\1[REDACTED]\2', 0),
        (r'(?i)((?:--password(?:=|\s+)|(?<!\w)-p(?=\S)))[^\s;]+', r'\1[REDACTED]', 0),
        (r'(?im)^(.*\b(?:Cookie|Set-Cookie)\s*:).*$' , r'\1 [REDACTED]', 0),
        (r'(?i)(define\s*\(\s*["\x27]' + SECRET + r'["\x27]\s*,\s*)(["\x27])[^\r\n]*?\2',
         r'\1\2[REDACTED]\2', 0)]
    count = 0
    for pattern, replacement, flags in patterns:
        text, changed = re.subn(pattern, replacement, text, flags=flags)
        count += changed
    return text, count


def command(argv):
    """No shell, stdin prompts or unlimited waits. Failures stay visible."""
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            return {'command': argv, 'error': 'timed out'}
        out, n1 = redact(stdout.decode('utf-8', 'replace'))
        err, n2 = redact(stderr.decode('utf-8', 'replace'))
        return {'command': argv, 'exit_code': process.returncode,
                'stdout': out[:150000], 'stderr': err[:20000],
                'output_truncated': len(out) > 150000 or len(err) > 20000,
                'redactions': n1 + n2}
    except OSError as exc:
        return {'command': argv, 'error': type(exc).__name__}


def private_write(path, data):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


class Collector(object):
    def __init__(self, output, manifest_only=False, limit=5000, byte_limit=64 * 1024 * 1024):
        self.output, self.manifest_only, self.limit = output, manifest_only, limit
        self.files, self.issues, self.seen = [], [], set()
        self.byte_limit, self.bytes_read = byte_limit, 0

    def limit_reached(self):
        if len(self.files) < self.limit:
            return False
        message = 'File-count limit reached; collection may be incomplete'
        if message not in self.issues:
            self.issues.append(message)
        return True

    def file(self, path, explicit=False):
        path = os.path.abspath(path)
        if path in self.seen:
            return
        self.seen.add(path)
        if self.limit_reached():
            return
        entry = {'path': path, 'realpath': os.path.realpath(path), 'content_copied': False}
        self.files.append(entry)
        try:
            info = os.lstat(path)
            entry.update(mode=oct(stat.S_IMODE(info.st_mode)), uid=info.st_uid,
                         gid=info.st_gid, size=info.st_size, mtime=info.st_mtime)
            if stat.S_ISLNK(info.st_mode):
                entry.update(kind='symlink', target=os.readlink(path), reason='Link recorded, not followed')
                return
            if not stat.S_ISREG(info.st_mode):
                entry.update(kind='special', reason='Not a regular file')
                return
            entry['kind'] = 'file'
            name = os.path.basename(path)
            if PRIVATE_NAMES.search(name):
                entry['reason'] = 'Sensitive filename: contents and digest withheld'
                return
            if info.st_size > 2 * 1024 * 1024:
                entry['reason'] = 'Over 2 MiB: contents/digest omitted to limit production I/O'
                return
            if self.bytes_read + info.st_size > self.byte_limit:
                entry['reason'] = 'Aggregate read limit reached: contents/digest omitted'
                if 'Aggregate read limit reached; collection incomplete' not in self.issues:
                    self.issues.append('Aggregate read limit reached; collection incomplete')
                return
            with open(path, 'rb') as stream:
                raw = stream.read(2 * 1024 * 1024 + 1)
            self.bytes_read += len(raw)
            if len(raw) > 2 * 1024 * 1024:
                entry['reason'] = 'File grew over size limit'
                return
            entry['sha256_original'] = hashlib.sha256(raw).hexdigest()
            permitted = explicit or name.endswith(TEXT_EXTENSIONS) or name in ('.htaccess', 'autostart')
            if self.manifest_only or not permitted:
                entry['reason'] = 'Manifest only / data or non-source content omitted'
                return
            if b'\x00' in raw:
                entry['reason'] = 'Binary content omitted'
                return
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                entry['reason'] = 'Non-UTF-8 source: request a separately reviewed copy'
                return
            sanitized, count = redact(text)
            data = sanitized.encode('utf-8')
            relative = 'files/' + path.lstrip('/').replace(os.sep, '/')
            private_write(os.path.join(self.output, relative), data)
            entry.update(content_copied=True, archive_path=relative, redactions=count,
                         sha256_collected=hashlib.sha256(data).hexdigest(),
                         changed_during_read=os.stat(path).st_mtime != info.st_mtime)
        except (OSError, IOError) as exc:
            entry['error'] = type(exc).__name__
            self.issues.append('Cannot collect ' + path + ': ' + type(exc).__name__)

    def tree(self, root, config=False):
        if not os.path.lexists(root):
            self.issues.append('Missing requested path: ' + root)
            return
        if not os.path.isdir(root):
            self.file(root, explicit=config)
            return
        if os.path.islink(root):
            self.file(root)
            self.issues.append('Directory symlink not followed; review target: ' + root)
            return
        def failed(error):
            self.issues.append('Directory not readable: ' + str(error.filename))
        for parent, dirs, names in os.walk(root, followlinks=False, onerror=failed):
            dirs[:] = sorted(name for name in dirs if name.lower() not in EXCLUDED_DIRS
                             and (os.path.islink(os.path.join(parent, name)) or
                                  os.path.realpath(os.path.join(parent, name)) != os.path.realpath(self.output)))
            for name in list(dirs):
                if os.path.islink(os.path.join(parent, name)):
                    self.file(os.path.join(parent, name))
                    dirs.remove(name)
            for name in sorted(names):
                # Unknown extensions are inventoried, never copied implicitly.
                config_source = config and (name.endswith(('.conf', '.load', '.ini', '.cnf', '.desktop'))
                                            or not os.path.splitext(name)[1])
                self.file(os.path.join(parent, name), explicit=config_source)
                if self.limit_reached():
                    return
            if self.limit_reached():
                return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', required=True, choices=['proxy', 'cdu'])
    parser.add_argument('--manifest-only', action='store_true', help='Hashes/metadata only; no application/config bodies')
    parser.add_argument('--source-root', action='append', default=[], help='Additional exact application directory; never a filesystem/home root')
    parser.add_argument('--output-parent', default=tempfile.gettempdir())
    args = parser.parse_args()
    for root in args.source_root:
        if not os.path.isabs(root) or os.path.realpath(root) in ('/', '/etc', '/var', '/home', '/opt', '/usr', '/tmp'):
            parser.error('--source-root must be an absolute, specific application path')
    os.umask(0o077)
    hostname = re.sub(r'[^A-Za-z0-9_.-]', '_', socket.gethostname())
    output = tempfile.mkdtemp(prefix='xhibit-evidence-' + hostname + '-', dir=args.output_parent)
    collector = Collector(output, args.manifest_only)
    roots = ROOTS[args.role] + args.source_root
    for root in roots:
        collector.tree(root)
    for path in COMMON_CONFIG:
        if os.path.lexists(path):
            collector.file(path, explicit=True)
    for root in CONFIG_ROOTS:
        if os.path.isdir(root):
            collector.tree(root, config=True)
    # Only XHIBIT-related scheduler files, never job execution or full user homes.
    scheduler_paths = list(SCHEDULER_FILES)
    for root in SCHEDULER_ROOTS:
        if not os.path.isdir(root):
            continue
        try:
            names = os.listdir(root)
        except OSError:
            collector.issues.append('Scheduler directory not readable: ' + root)
            continue
        scheduler_paths.extend(os.path.join(root, name) for name in sorted(names))
    for path in scheduler_paths:
        if not os.path.isfile(path) or os.path.islink(path):
            continue
        try:
            with open(path, 'rb') as stream:
                if re.search(b'xhibit|court-display|updatechecksums|PDManager|Checksum', stream.read(65536), re.I):
                    collector.file(path, explicit=True)
        except IOError:
            collector.issues.append('Scheduler file not readable: ' + path)
    runtime = dict(collected_at=datetime.datetime.utcnow().isoformat() + 'Z',
                   role=args.role, hostname=socket.gethostname(), uid=os.getuid(),
                   python=sys.version, python_executable=sys.executable, system=platform.platform())
    probes = [['id'], ['uname', '-a'], ['getenforce'], ['getsebool', '-a'],
              ['ip', 'address', 'show'], ['ip', 'route'], ['ss', '-lntp'],
              ['ps', '-eZ'], ['php', '-v'], ['xsltproc', '--version']]
    apache = shutil.which('httpd') or shutil.which('apache2')
    if apache:
        probes.extend([[apache, '-V'], [apache, '-M'], [apache, '-S']])
    if shutil.which('rpm'):
        probes.append(['rpm', '-q', 'httpd', 'php', 'python34', 'libxml2', 'libxslt', 'mariadb-server'])
    elif shutil.which('dpkg-query'):
        probes.append(['dpkg-query', '-W', 'apache2', 'python3', 'libxml2', 'libxslt1.1', 'xsltproc'])
    runtime['probes'] = [command(probe) for probe in probes]
    runtime['libraries'] = {}
    for name in ('bs4', 'pymysql'):
        try:
            module = __import__(name)
            runtime['libraries'][name] = dict(version=getattr(module, '__version__', 'unknown'),
                                               file=getattr(module, '__file__', 'unknown'))
        except Exception as exc:
            runtime['libraries'][name] = dict(error=type(exc).__name__)
    runtime['git'] = [command(['git', '--git-dir=' + os.path.join(root, '.git'), 'rev-parse', 'HEAD'])
                      for root in roots if os.path.isdir(os.path.join(root, '.git'))]
    manifest = dict(files=collector.files, incomplete=collector.issues,
                    notes=['Original hashes identify byte differences; collected text may be redacted.',
                           'HTML/XML/JSON/data/binary assets are metadata-only unless an explicitly named system config.',
                           'Missing paths and permission errors need review, not permission changes.',
                           'No root directory symlinks followed; add reviewed actual targets with --source-root.',
                           'Read-only collection can update normal filesystem access times.'])
    for name, data in [('runtime.json', runtime), ('manifest.json', manifest)]:
        private_write(os.path.join(output, name), json.dumps(data, sort_keys=True, indent=2).encode('utf-8'))
    private_write(os.path.join(output, 'REVIEW_BEFORE_SHARING.txt'),
        b'PRIVATE EVIDENCE, NOT A DEPLOYMENT PACKAGE. Automatic redaction is best-effort.\n'
        b'Review every collected file for credentials, personal data and internal information before sharing.\n'
        b'No application files were executed or changed. No database rows, screenshots, logs, keys or password files requested.\n'
        b'Check manifest.json incomplete/errors and runtime.json probe failures. Missing evidence is not a pass.\n')
    archive_path = output + '.tar.gz'
    fd = os.open(archive_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            archive.add(output, arcname=os.path.basename(output), recursive=True)
    digest_state = hashlib.sha256()
    with open(archive_path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest_state.update(chunk)
    digest = digest_state.hexdigest()
    private_write(archive_path + '.sha256',
                  (digest + '  ' + os.path.basename(archive_path) + '\n').encode('ascii'))
    print(json.dumps(dict(directory=output, archive=archive_path, checksum=archive_path + '.sha256',
                         files=len(collector.files), incomplete=len(collector.issues),
                         review_required=True), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
