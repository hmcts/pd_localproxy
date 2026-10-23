#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare pinned public GitHub source with deployed files over SSH from JBOX.

Python 3.4+, standard library only. No Git installation needed. Only the machine
preparing the public baseline needs HTTPS access. Production is read-only: the
helper runs in memory, never deploys, executes application code or restarts a
service. Reports and optional redacted diffs stay on the comparison machine.
"""
import sys
if sys.version_info < (3, 4):
    sys.exit('Python 3.4+ required; do not install or upgrade without approval.')
import argparse
import base64
import collections
import configparser
import datetime
import difflib
import hashlib
import io
import json
import os
import posixpath
import re
import shlex
import shutil
import socket
import stat
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request

REPOSITORIES = {'proxy': 'hmcts/pd_localproxy', 'cdu': 'hmcts/pd_cdu'}
CODE = ('.php', '.py', '.cgi', '.sh', '.bash', '.js', '.css', '.xsl', '.xslt')
ASSETS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.otf', '.eot')
EXCLUDED_DIRS = set(['.git', '.svn', '__pycache__', 'logs', 'log', 'cache', 'tmp',
    'temp', 'uploads', 'upload', 'screenshots', 'captures', 'sessions', 'node_modules',
    '.ssh', 'private', 'testdata', 'test-data'])
PRIVATE = re.compile(r'(?i)(?:^\.env(?:\.|$)|passwd|password|shadow|private.key|'
                     r'id_rsa|id_ed25519|\.pem$|\.key$|\.p12$|\.pfx$|\.jks$|keystore)')
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_FILES = 5000
MARKER = 'XHIBIT_COMPARE_V1\n'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def eligible(path):
    parts = path.replace('\\', '/').split('/')
    if any(part.lower() in EXCLUDED_DIRS for part in parts[:-1]):
        return False
    name = parts[-1]
    return not PRIVATE.search(name) and (name.lower().endswith(CODE + ASSETS) or name == '.htaccess')


def code_file(path):
    return path.lower().endswith(CODE) or posixpath.basename(path) == '.htaccess'


def safe_relative(path):
    return (bool(path) and not path.startswith('/') and '\\' not in path
            and not any(part in ('', '.', '..') for part in path.split('/'))
            and not any(ord(char) < 32 for char in path))


# BEGIN SHARED REDACTION: keep byte-identical in collect_production.py and
# compare_github.py (a test enforces this). Each tool runs on the target as one
# standalone file, so neither can import the other.
REDACT_SECRET = (r'(?:[\w.-]*(?:pass|pwd|secret|token|credential|api[_-]?key)[\w.-]*'
                 r'|DBusername|dbuser)')
REDACTIONS = [
    (r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', '[REDACTED PRIVATE KEY]', re.S),
    (r'(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+(?::[^\s/@]*)?@', r'\1[REDACTED]@', 0),
    (r'(?im)^(\s*' + REDACT_SECRET + r'\s*[=:]\s*).*$', r'\1[REDACTED]', 0),
    (r'(?i)((?:[\w$]+[.\[\]"\x27]*)?' + REDACT_SECRET + r'[\]"\x27]*\s*(?:=>|=|:)\s*)(["\x27])[^\r\n]*?\2',
     r'\1\2[REDACTED]\2', 0),
    (r'(?i)(\b(?:[\w.-]*pass[\w.-]*|pwd|user(?:name)?)\s*=\s*)([^;\s&"\x27<>]+)', r'\1[REDACTED]', 0),
    # Tomcat server.xml/context.xml: keystorePass, truststorePass, keyPass, username="...".
    (r'(?i)(\b[\w.-]*(?:pass|user(?:name)?)\s*=\s*)(["\x27])[^\r\n]*?\2', r'\1\2[REDACTED]\2', 0),
    (r'(?im)^([ \t]*(?:SetEnv|SetEnvIf)\s+' + REDACT_SECRET + r'\s+).*$', r'\1[REDACTED]', 0),
    (r'(?im)^([ \t]*AuthLDAPBindPassword\s+).*$', r'\1[REDACTED]', 0),
    (r'(?i)(Authorization[\s:"\x27=]+(?:Basic|Bearer)\s+)[^\s"\x27<>]+', r'\1[REDACTED]', 0),
    (r'(?i)(<' + REDACT_SECRET + r'>)[^<]*(</[^>]+>)', r'\1[REDACTED]\2', 0),
    (r'(?i)((?:--password(?:=|\s+)|(?<!\w)-p(?=\S)))[^\s;]+', r'\1[REDACTED]', 0),
    (r'(?im)^(.*\b(?:Cookie|Set-Cookie)\s*:).*$', r'\1 [REDACTED]', 0),
    # PHP constants, e.g. define('DB_PASS', '...').
    (r'(?i)(define\s*\(\s*["\x27]' + REDACT_SECRET + r'["\x27]\s*,\s*)(["\x27])[^\r\n]*?\2',
     r'\1\2[REDACTED]\2', 0)]


def redact_with_count(text):
    """Best-effort credential redaction returning (text, replacements); review output manually."""
    count = 0
    for pattern, replacement, flags in REDACTIONS:
        text, changed = re.subn(pattern, replacement, text, flags=flags)
        count += changed
    return text, count
# END SHARED REDACTION


def redact(text):
    """Best-effort only. Diffs require manual review before sharing."""
    return redact_with_count(text)[0]


def fetch(url, limit):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'XHIBIT-read-only-baseline-comparison', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('GitHub response exceeds the collection size limit')
    return raw


def github_baseline(role, ref):
    repo = REPOSITORIES[role]
    print('Resolving {0} at {1}'.format(repo, ref), file=sys.stderr)
    commit = json.loads(fetch('https://api.github.com/repos/' + repo + '/commits/' +
                              urllib.parse.quote(ref, safe=''), 1024 * 1024).decode('utf-8'))['sha']
    if not re.match(r'^[0-9a-f]{40}$', commit):
        raise ValueError('GitHub did not return a full commit SHA')
    raw = fetch('https://codeload.github.com/' + repo + '/tar.gz/' + commit, 32 * 1024 * 1024)
    files, excluded, total = [], [], 0
    expected_root = repo.split('/')[1] + '-' + commit
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for index, member in enumerate(archive):
            if index > MAX_FILES:
                raise ValueError('GitHub archive has too many entries')
            if member.isdir():
                continue
            root, separator, path = member.name.partition('/')
            if root != expected_root or not separator or not safe_relative(path):
                raise ValueError('Unsafe/unexpected path in GitHub archive')
            if not member.isfile():
                excluded.append({'path': path, 'reason': 'Repository link/special file not followed'})
                continue
            if not eligible(path):
                excluded.append({'path': path, 'reason': 'Configuration/data/non-application file excluded'})
                continue
            total += member.size
            if member.size > MAX_FILE or total > MAX_TOTAL:
                raise ValueError('GitHub source exceeds the collection size limit')
            content = archive.extractfile(member).read(MAX_FILE + 1)
            files.append(dict(path=path, sha256=digest(content), size=len(content),
                              content_b64=base64.b64encode(content).decode('ascii')))
    if not files:
        raise ValueError('No application source found in GitHub archive')
    return dict(repository=repo, requested_ref=ref, commit=commit,
                commit_url='https://github.com/' + repo + '/commit/' + commit,
                files=sorted(files, key=lambda item: item['path']), excluded=excluded)


def validate_baseline(baselines):
    if not isinstance(baselines, dict) or not baselines:
        raise ValueError('Baseline must contain at least one known repository')
    if sum(len(baseline.get('files', [])) for baseline in baselines.values()) > MAX_FILES:
        raise ValueError('Combined baseline exceeds the file-count limit')
    for role, baseline in baselines.items():
        if role not in REPOSITORIES or baseline.get('repository') != REPOSITORIES[role]:
            raise ValueError('Unexpected repository in baseline')
        if not re.match(r'^[0-9a-f]{40}$', baseline.get('commit', '')):
            raise ValueError('Baseline must be pinned to a full commit SHA')
        seen, total = set(), 0
        if not baseline.get('files') or len(baseline['files']) > MAX_FILES:
            raise ValueError('Invalid baseline file count')
        for entry in baseline['files']:
            path = entry['path']
            if not safe_relative(path) or not eligible(path) or path in seen:
                raise ValueError('Unsafe, excluded or duplicate baseline path')
            seen.add(path)
            content = base64.b64decode(entry['content_b64'].encode('ascii'), validate=True)
            total += len(content)
            if len(content) > MAX_FILE or total > MAX_TOTAL or digest(content) != entry['sha256']:
                raise ValueError('Baseline content/hash/size check failed')


def read_file(path, budget):
    """Do not follow any symlink component, including a symlinked webroot."""
    entry = {'server_path': path}
    try:
        current = '/'
        for component in path.lstrip('/').split('/'):
            current = posixpath.join(current, component)
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode):
                entry.update(status='symlink_unchecked', link=current, target=os.readlink(current))
                return entry, None
        entry.update(size=info.st_size, mode=oct(stat.S_IMODE(info.st_mode)),
                     uid=info.st_uid, gid=info.st_gid, mtime=info.st_mtime)
        if not stat.S_ISREG(info.st_mode):
            entry['status'] = 'not_regular'
            return entry, None
        if info.st_size > MAX_FILE or budget[0] + info.st_size > MAX_TOTAL:
            entry['status'] = 'size_limit_unchecked'
            return entry, None
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                entry['status'] = 'changed_during_read'
                return entry, None
            raw = stream.read(MAX_FILE + 1)
            after = os.fstat(stream.fileno())
        budget[0] += len(raw)
        if len(raw) > MAX_FILE or (opened.st_size, opened.st_mtime) != (after.st_size, after.st_mtime):
            entry['status'] = 'changed_during_read'
            return entry, None
        entry.update(status='read', production_sha256=digest(raw))
        return entry, raw
    except OSError as exc:
        entry.update(status='missing' if exc.errno == 2 else 'unreadable', error=type(exc).__name__)
        return entry, None


def validate_root(path):
    if (not path.startswith('/') or posixpath.normpath(path) != path or '\\' in path
            or any(ord(char) < 32 for char in path)
            or path in ('/', '/etc', '/var', '/home', '/opt', '/usr', '/tmp', '/var/www')):
        raise ValueError('Use a specific absolute production application path: ' + path)
    return path


def mapped_path(role, path, locations):
    if role == 'cdu':
        return posixpath.join(locations['cdu_root'], path)
    if path == 'proxy/xhibit.py':
        return locations['parser_file']
    for prefix, key in [('proxy/', 'proxy_root'), ('manager/', 'manager_root'), ('updatescripts/', 'updatescripts_root')]:
        if path.startswith(prefix):
            return posixpath.join(locations[key], path[len(prefix):]) if locations.get(key) else None
    return None


def inventory(root, issues):
    try:
        # Check every component before os.walk, which otherwise follows root links.
        current = '/'
        for component in root.lstrip('/').split('/'):
            current = posixpath.join(current, component)
            if os.path.islink(current):
                issues.append('Inventory symlink not followed: ' + current + ' -> ' + os.readlink(current))
                return
        if not os.path.exists(root):
            issues.append('Inventory root missing: ' + root)
            return
        if os.path.isfile(root):
            if eligible(posixpath.basename(root)):
                yield root
            return
        def failed(error):
            issues.append('Inventory unreadable: ' + str(error.filename))
        for parent, dirs, names in os.walk(root, followlinks=False, onerror=failed):
            keep = []
            for name in sorted(dirs):
                path = os.path.join(parent, name)
                if name.lower() in EXCLUDED_DIRS:
                    continue
                if os.path.islink(path):
                    issues.append('Inventory directory symlink not followed: ' + path)
                else:
                    keep.append(name)
            dirs[:] = keep
            for name in sorted(names):
                if eligible(name):
                    yield os.path.join(parent, name)
    except OSError as exc:
        issues.append('Inventory failed: ' + root + ': ' + type(exc).__name__)


def compare_on_server(payload):
    baselines, locations = payload['baselines'], payload['locations']
    validate_baseline(baselines)
    for path in locations.values():
        if path:
            validate_root(path)
    files, extra, issues, checked, budget = [], [], [], set(), [0]
    diff_budget = 1024 * 1024
    for role in sorted(baselines):
        for expected in baselines[role]['files']:
            repo_path = expected['path']
            path = mapped_path(role, repo_path, locations)
            base = dict(role=role, repository=REPOSITORIES[role], repo_path=repo_path,
                        github_sha256=expected['sha256'])
            if not path:
                base.update(status='unmapped_unchecked', server_path=None)
                files.append(base)
                continue
            checked.add(path)
            actual, raw = read_file(path, budget)
            base.update(actual)
            if raw is not None:
                base['status'] = 'identical' if digest(raw) == expected['sha256'] else 'different'
                if base['status'] == 'different':
                    original = base64.b64decode(expected['content_b64'].encode('ascii'))
                    base['equal_after_crlf_normalization'] = original.replace(b'\r\n', b'\n') == raw.replace(b'\r\n', b'\n')
                    if payload.get('include_diffs') and code_file(repo_path) and diff_budget <= 0:
                        base['diff_truncated'] = True
                    elif payload.get('include_diffs') and code_file(repo_path):
                        try:
                            left, right = original.decode('utf-8'), raw.decode('utf-8')
                            if '\x00' in left or '\x00' in right:
                                raise UnicodeError('Binary')
                            # Redact whole files BEFORE selecting diff lines/context.
                            diff = ''.join(difflib.unified_diff(redact(left).splitlines(True),
                                redact(right).splitlines(True), fromfile='GitHub/' + repo_path,
                                tofile='production' + path, n=3))
                            encoded = diff.encode('utf-8')
                            allowance = min(32768, diff_budget)
                            if len(encoded) > allowance:
                                base['diff_truncated'] = True
                            base['redacted_diff'] = encoded[:allowance].decode('utf-8', 'replace')
                            diff_budget -= min(len(encoded), allowance)
                            if not diff:
                                base['diff_note'] = 'Raw bytes differ; redaction or line representation hides the difference'
                        except UnicodeError:
                            base['diff_note'] = 'Binary/non-UTF-8: hash comparison only'
            files.append(base)
    roots = []
    if 'proxy' in baselines:
        roots.extend([locations['proxy_root'], locations['manager_root'],
                      posixpath.dirname(locations['parser_file'])])
        if locations.get('updatescripts_root'):
            roots.append(locations['updatescripts_root'])
        roots.extend(payload.get('extra_roots', []))
    if 'cdu' in baselines:
        roots.append(locations['cdu_root'])
    for root in sorted(set(roots)):
        validate_root(root)
        for path in inventory(root, issues):
            if path in checked:
                continue
            if len(checked) >= MAX_FILES:
                issues.append('File-count limit reached; extra-file inventory incomplete')
                break
            checked.add(path)
            actual, raw = read_file(path, budget)
            if raw is not None:
                actual['status'] = 'production_only'
            extra.append(actual)
    result = dict(files=files, production_only=extra, issues=sorted(set(issues)),
                server=dict(hostname=socket.gethostname(), python=sys.version,
                            python_executable=sys.executable, uid=os.getuid()),
                bytes_read=budget[0])
    if payload.get('collect_evidence'):
        result['targeted_evidence'] = targeted_evidence(locations)
    return result


def ini_values(raw):
    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str
    parser.read_string('[XHIBIT_DEFAULT]\n' + raw.decode('utf-8-sig'))
    return {key: value.strip().strip('"\'') for section in parser.sections()
            for key, value in parser.items(section)}


def schema_metadata(values):
    """Existing local DB account, metadata only. Never query application records."""
    import pymysql
    dsn = values['DBConn']
    if not dsn.startswith('mysql:'):
        raise ValueError('Unsupported configured database')
    fields = dict(part.split('=', 1) for part in dsn[6:].split(';') if '=' in part)
    if fields.get('host', 'localhost') not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Remote DB requires a separately reviewed metadata collection')
    connection = pymysql.connect(host=fields.get('host', 'localhost'), port=int(fields.get('port', 3306)),
                                 user=values['DBusername'], password=values['DBpasswd'], db=values['DBName'],
                                 connect_timeout=5, read_timeout=10, charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor)
    try:
        cursor = connection.cursor()
        try:
            result = {}
            for name, sql in [
                    ('columns', 'SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,IS_NULLABLE,COLLATION_NAME '
                     'FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME,ORDINAL_POSITION LIMIT 2000'),
                    ('indexes', 'SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME '
                     'FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX LIMIT 2000'),
                    ('tables', 'SELECT TABLE_NAME,ENGINE,TABLE_COLLATION FROM information_schema.TABLES '
                     'WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME LIMIT 500')]:
                cursor.execute(sql, (values['DBName'],))
                result[name] = cursor.fetchall()
            return result
        finally:
            cursor.close()
    finally:
        connection.close()


def targeted_evidence(locations):
    """Bounded additional evidence; no archive transfer, writes or privilege escalation."""
    result = {'configurations': [], 'callers': [], 'issues': [],
              'scope': 'Selected config keys, local schema metadata, bounded caller/updater search; NOT a complete PHP consumer audit'}
    selected = set('DB_INI_FILE PARSER_SCRIPT fetch timeout lastUpdatedLocation timestampMonitorFile default_charset default_mimetype display_errors'.split())
    budget = [0]
    paths = [posixpath.join(locations['proxy_root'], 'proxy.ini'),
             posixpath.join(posixpath.dirname(locations['parser_file']), 'ops.ini'),
             posixpath.join(locations['cdu_root'], 'cdu.ini'), '/etc/php.ini']
    for path in paths:
        entry, raw = read_file(path, budget)
        if raw is not None:
            try:
                values = ini_values(raw)
                safe = {key: redact(value) for key, value in values.items() if key in selected}
                if 'fetch' in safe:
                    url = urllib.parse.urlsplit(values['fetch'])
                    safe['fetch'] = urllib.parse.urlunsplit((url.scheme, url.netloc.rsplit('@', 1)[-1], url.path, '', ''))
                # Never export arbitrary configured shell commands or DB credentials.
                if 'macAddressCmd' in values:
                    safe['macAddressCmd'] = '[configured; obtain a manually reviewed copy]'
                entry['reviewed_keys_only'] = safe
                entry['redacted_values_sha256'] = digest(json.dumps(safe, sort_keys=True).encode('utf-8'))
                if path == paths[1]:
                    try: result['schema_metadata'] = schema_metadata(values)
                    except Exception as exc: result['issues'].append('Schema metadata unavailable: ' + type(exc).__name__)
            except (ValueError, UnicodeError, configparser.Error) as exc:
                entry['parse_error'] = type(exc).__name__
        result['configurations'].append(entry)
    roots = ['/etc/cron.d', '/etc/systemd/system', '/usr/lib/systemd/system',
             '/home/xhibit/bin', '/opt/updatechecksums', '/var/www/cgi-bin']
    pattern = re.compile(r'cgi-bin/xhibit|xhibit\.py|cdu\.tar|CDUApplicationUpdate|LocalproxyApplicationUpdate|PDManagerUpdate|DownloadUpdates')
    candidates = ['/etc/crontab', '/etc/rc.d/rc.local']
    for root in roots:
        if not os.path.isdir(root) or os.path.islink(root):
            result['issues'].append('Caller location absent/unavailable: ' + root)
            continue
        def failed(error):
            result['issues'].append('Caller directory unreadable: ' + str(error.filename))
        for parent, dirs, names in os.walk(root, followlinks=False, onerror=failed):
            dirs[:] = sorted(name for name in dirs if not os.path.islink(os.path.join(parent, name))) if parent[len(root):].count('/') < 2 else []
            for name in sorted(names):
                if PRIVATE.search(name) or name.endswith(('.ini', '.log', '.sql', '.tar', '.gz', '.png')):
                    continue
                candidates.append(os.path.join(parent, name))
            if len(candidates) > 300:
                result['issues'].append('Caller file-count limit reached')
                break
    for path in candidates[:300]:
        if budget[0] > 2 * 1024 * 1024:
            result['issues'].append('Caller byte limit reached')
            break
        entry, raw = read_file(path, budget)
        if raw is None:
            result['issues'].append('Caller file unchecked: ' + path + ' (' + entry['status'] + ')')
        elif len(raw) <= 65536 and b'\0' not in raw:
            matches = [{'line': index + 1, 'text': redact(line)[:1000]}
                       for index, line in enumerate(raw.decode('utf-8', 'replace').splitlines()) if pattern.search(line)]
            if matches:
                entry['matching_lines'] = matches[:30]
                result['callers'].append(entry)
    result['issues'].append('Root crontab, protected backups, physical CDU and external PHP consumers remain explicit operator checks')
    return result


def ssh_command(args):
    if not re.match(r'^[A-Za-z0-9_.:-]+$', args.host) or args.host.startswith('-'):
        raise ValueError('Use a hostname or IP address, not a shell command/user@host')
    if not 1 <= args.port <= 65535:
        raise ValueError('Invalid SSH port')
    validate_root(args.remote_python)
    executable = args.ssh_executable or ('plink' if args.ssh_client == 'plink' else 'ssh')
    if not shutil.which(executable):
        raise ValueError('SSH client not found; use an existing approved client, do not install automatically')
    if args.ssh_client == 'plink':
        command = [executable, '-ssh', '-T', '-P', str(args.port)]
    else:
        command = [executable, '-T', '-o', 'ConnectTimeout=15', '-p', str(args.port)]
    if args.user:
        command.extend(['-l', args.user])
    for option in args.ssh_option:
        command.append(option)
    bootstrap = "import sys,base64;exec(compile(base64.b64decode(sys.stdin.buffer.readline()),'<xhibit-read-only-compare>','exec'))"
    remote = shlex.quote(args.remote_python) + ' -B -c ' + shlex.quote(bootstrap) + ' --remote'
    command.extend([args.host, remote])
    return command


def run_remote(args, payload):
    with open(os.path.abspath(__file__), 'rb') as stream:
        source = stream.read()
    request = base64.b64encode(source) + b'\n' + json.dumps(payload).encode('utf-8')
    print('Reading files over SSH; no production files will be written. Authenticate normally.', file=sys.stderr)
    process = subprocess.Popen(ssh_command(args), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        stdout, unused_stderr = process.communicate(request, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise ValueError('SSH comparison timed out; no complete comparison report')
    if process.returncode:
        raise ValueError('SSH/helper failed (exit {0}); no successful comparison'.format(process.returncode))
    if len(stdout) > 32 * 1024 * 1024 or MARKER.encode('ascii') not in stdout:
        raise ValueError('Unexpected/oversized SSH response; no successful comparison')
    response = stdout.split(MARKER.encode('ascii'), 1)[1]
    return json.loads(response.decode('utf-8'))


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


def summarize(result):
    counts = collections.Counter(item['status'] for item in result['files'])
    extra_counts = collections.Counter(item['status'] for item in result['production_only'])
    incomplete = (bool(result['issues']) or bool(result.get('targeted_evidence', {}).get('issues'))
                  or any(status not in ('identical', 'different', 'missing') for status in counts)
                  or any(status != 'production_only' for status in extra_counts))
    differences = counts['different'] + counts['missing'] + extra_counts['production_only']
    return dict(file_statuses=dict(counts), extra_file_statuses=dict(extra_counts),
                incomplete=incomplete, exit_code=3 if incomplete else (1 if differences else 0))


def text_report(report):
    lines = ['XHIBIT GitHub versus deployed files',
             'Target: ' + report['target'], 'Collected: ' + report['collected_at'], '']
    for role, baseline in sorted(report['baselines'].items()):
        lines.append('{0}: {1} ({2})'.format(baseline['repository'], baseline['commit'], baseline['requested_ref']))
    lines.extend(['', 'Summary: ' + json.dumps(report['summary'], sort_keys=True),
                  'File equality is NOT proof of behaviour, live routing or vulnerability removal.',
                  'Mappings must be checked against Apache configuration; no HTTP endpoints were exercised.',
                  'INI/SQL/case data/logs/password files are excluded. Optional diffs need manual secret review.', ''])
    for item in report['files']:
        if item['status'] != 'identical':
            lines.append('{0}: {1}:{2} -> {3}'.format(item['status'], item['repository'],
                         item['repo_path'], item.get('server_path') or '(mapping required)'))
            if item.get('equal_after_crlf_normalization'):
                lines.append('  Raw bytes differ; equal after CRLF-only normalization (still a difference).')
            if 'redacted_diff' in item:
                lines.append(item['redacted_diff'])
            if item.get('diff_truncated'):
                lines.append('  DIFF TRUNCATED; request a reviewed copy for full analysis.')
    lines.append('\nAdditional production files in inspected locations (not necessarily active):')
    for item in report['production_only']:
        lines.append('{0}: {1}'.format(item['status'], item['server_path']))
    lines.append('\nIncomplete inventory / warnings:')
    lines.extend(report['issues'] or ['None recorded for the selected scope.'])
    if 'targeted_evidence' in report:
        lines.append('\nTargeted evidence is in report.json; manually review before sharing. Outstanding checks:')
        lines.extend(report['targeted_evidence']['issues'])
    return '\n'.join(lines) + '\n'


def build_report(payload, result):
    report = dict(schema_version=1, collected_at=datetime.datetime.utcnow().isoformat() + 'Z',
                  target=payload.get('target', result['server']['hostname']), locations=payload['locations'],
                  baselines={role: {key: value for key, value in baseline.items() if key != 'files'}
                             for role, baseline in payload['baselines'].items()})
    report.update(result)
    report['summary'] = summarize(result)
    return report


def main():
    if sys.argv[1:] == ['--remote']:
        payload = json.loads(sys.stdin.buffer.read().decode('utf-8'))
        result = compare_on_server(payload)
        report = build_report(payload, result)
        sys.stdout.write(MARKER + json.dumps(dict(report=report, report_text=text_report(report)), sort_keys=True))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action')
    prepare = sub.add_parser('prepare', help='Download a public, pinned baseline; no SSH connection')
    prepare.add_argument('--output', required=True)
    compare = sub.add_parser('compare', help='Run from JBOX against an approved production SSH target')
    for command in (prepare, compare):
        command.add_argument('--only', choices=['proxy', 'cdu', 'both'], default='both')
        command.add_argument('--proxy-ref', default='master')
        command.add_argument('--cdu-ref', default='master')
    compare.add_argument('--host', required=True, help='Proxy/CDU hostname or IP, reached FROM JBOX')
    compare.add_argument('--user', help='SSH login, including a domain if required')
    compare.add_argument('--port', type=int, default=22)
    compare.add_argument('--baseline', help='Offline baseline JSON made by prepare; skips ALL GitHub access')
    compare.add_argument('--include-diffs', action='store_true', help='Optional redacted changed-source snippets; manual review required')
    compare.add_argument('--collect-evidence', action='store_true', help='Additional selected config/schema metadata and bounded caller search, no database records')
    compare.add_argument('--output-parent', default='.')
    compare.add_argument('--timeout', type=int, default=180)
    compare.add_argument('--ssh-client', choices=['ssh', 'plink'], default='ssh')
    compare.add_argument('--ssh-executable', help='Path to an existing approved SSH/Plink executable')
    compare.add_argument('--ssh-option', action='append', default=[], help='Additional client argument; repeat, e.g. --ssh-option=-J --ssh-option=USER@PROXY')
    compare.add_argument('--remote-python', default='/usr/bin/python3')
    compare.add_argument('--proxy-root', default='/var/www/court-display/proxy')
    compare.add_argument('--parser-file', default='/var/www/court-display/proxycode/xhibit.py')
    compare.add_argument('--manager-root', default='/var/www/lan/manager')
    compare.add_argument('--cdu-root', default='/var/www/lan/cdu')
    compare.add_argument('--updatescripts-root', help='Exact deployed updater directory, once identified; otherwise reported UNCHECKED')
    args = parser.parse_args()
    if not args.action:
        parser.error('Choose prepare or compare')
    os.umask(0o077)
    try:
        roles = ['proxy', 'cdu'] if args.only == 'both' else [args.only]
        if args.action == 'compare' and args.baseline:
            if os.path.getsize(args.baseline) > 2 * MAX_TOTAL:
                raise ValueError('Offline baseline too large')
            with open(args.baseline, 'rb') as stream:
                bundle = json.loads(stream.read().decode('utf-8'))
            baselines = {role: bundle['baselines'][role] for role in roles}
        else:
            baselines = {role: github_baseline(role, getattr(args, role + '_ref')) for role in roles}
        validate_baseline(baselines)
        if args.action == 'prepare':
            private_write(args.output, json.dumps(dict(schema_version=1, baselines=baselines), sort_keys=True).encode('utf-8'))
            print('Public baseline saved: ' + os.path.abspath(args.output))
            for baseline in baselines.values():
                print(baseline['repository'] + ': ' + baseline['commit'])
            return 0
        locations = {name: getattr(args, name) for name in
                     ['proxy_root', 'parser_file', 'manager_root', 'cdu_root', 'updatescripts_root']}
        for path in locations.values():
            if path:
                validate_root(path)
        payload = dict(baselines=baselines, locations=locations, include_diffs=args.include_diffs,
                       collect_evidence=args.collect_evidence, target=args.host,
                       extra_roots=['/var/www/cgi-bin/xhibit.py', '/var/www/court-display/software', '/var/www/lan/xhibit'])
        response = run_remote(args, payload)
        report = response['report']
        output = tempfile.mkdtemp(prefix='xhibit-github-compare-', dir=args.output_parent)
        private_write(os.path.join(output, 'report.json'), json.dumps(report, indent=2, sort_keys=True).encode('utf-8'))
        private_write(os.path.join(output, 'report.txt'), response['report_text'].encode('utf-8'))
        print('Reports saved ON THIS MACHINE: ' + os.path.abspath(output))
        print(json.dumps(report['summary'], sort_keys=True))
        print('Review reports before sharing. No production files were written or services restarted.')
        return report['summary']['exit_code']
    except (OSError, ValueError, KeyError, tarfile.TarError) as exc:
        # Do not dump SSH output, source text or credential-bearing exception URLs.
        print('Comparison failed: {0}: {1}'.format(type(exc).__name__,
              str(exc) if isinstance(exc, ValueError) else 'check connectivity, permissions, baseline and arguments'), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
