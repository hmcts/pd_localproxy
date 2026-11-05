#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Development-only loopback stack. Never use a deployed database configuration.

Requires an explicitly enabled disposable MySQL/MariaDB test service, Apache,
xsltproc, and the application's parser dependencies. No packages are installed.
"""
import argparse
import atexit
import base64
import binascii
import io
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
WORKSPACE = os.path.dirname(REPO)
sys.path.insert(0, os.path.join(REPO, 'python'))
sys.path.insert(0, os.path.join(REPO, 'migration', 'tests'))
from database import Database
from http_support import read_ini


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Feed(BaseHTTPRequestHandler):
    def do_GET(self):
        from test_compatibility import html_page, TITLES, WELSH_TITLES
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/selector.php':
            data = (b'<div class="display-location">Daily List</div>\n'
                    b'<a onClick=\'selectDisplay("english-0")\'>Daily List</a>')
        elif parsed.path == '/page.php':
            value = urllib.parse.parse_qs(parsed.query).get('uri', ['english-0'])[0]
            match = re.match(r'^(english|welsh)-([0-7])$', value)
            if not match:
                self.send_error(404)
                return
            welsh, index = match.group(1) == 'welsh', int(match.group(2))
            data = html_page((WELSH_TITLES if welsh else TITLES)[index], welsh)
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=UTF-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class LocalStack(object):
    mac = 'b8:27:eb:67:75:8f'
    user = 'operator'
    password = 'local-test-only'

    def __init__(self, config, with_manager=False):
        self.with_manager = with_manager
        self.settings = read_ini(config)
        if self.settings.get('AllowTestDatabases', '').lower() != 'true':
            raise ValueError('Dedicated config must set AllowTestDatabases=true')
        dsn = self.settings.get('DBConn', '')
        fields = dict(part.split('=', 1) for part in dsn[6:].split(';') if '=' in part)
        if fields.get('host') not in ('127.0.0.1', 'localhost', '::1') or fields.get('unix_socket'):
            raise ValueError('Local stack accepts only an explicit loopback test database')
        self.temp = tempfile.mkdtemp(prefix='xhibit-local-stack-')
        self.name = 'xhibit_test_' + uuid.uuid4().hex
        self.admin = self.db = self.feed = self.apache = self.apache_log = None
        self.created = False
        atexit.register(self.stop)

    def write(self, relative, data):
        path = os.path.join(self.temp, relative)
        with io.open(path, 'w', encoding='utf-8') as stream:
            stream.write(data)
        os.chmod(path, 0o600)
        return path

    def start(self):
        import pwd
        import grp
        self.admin = Database.from_values(self.settings)
        self.admin.execute('CREATE DATABASE ' + self.name + ' CHARACTER SET utf8mb4')
        self.created = True
        values = dict(self.settings, DBName=self.name)
        self.db = Database.from_values(values)
        with io.open(os.path.join(REPO, 'manager', 'xhibit_proxy_schema.sql'), encoding='utf-8') as stream:
            schema = re.sub(r'--[^\n]*', '', stream.read())
        for statement in schema.split(';'):
            if statement.strip():
                self.db.execute(statement)
        self.feed = ThreadedServer(('127.0.0.1', 0), Feed)
        threading.Thread(target=self.feed.serve_forever, daemon=True).start()
        self.feed_url = 'http://127.0.0.1:' + str(self.feed.server_port)
        self.proxy_url = 'http://127.0.0.1:' + str(port())
        self.cdu_url = 'http://127.0.0.1:' + str(port())
        self.db.execute('INSERT INTO SITE (title,welshTitle,xsl,selectorUrl,pageUrl,powersaveSchedule) '
                        'VALUES (%s,%s,%s,%s,%s,%s)',
                        ('Local Test Court', 'Llys Prawf', 'new', self.feed_url + '/selector.php',
                         self.feed_url + '/page.php?', '[]'))
        self.db.execute('INSERT INTO CDU (macAddress,title,cduNumber,location,url,refresh,ipAddr,fkSITE) '
                        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                        (self.mac, 'Local Test Screen', 'TESTDISPL01', 'Reception', 'english-0;welsh-0', 15, '127.0.0.1', 1))
        self.db.execute('INSERT INTO urlMappings (cduID,url) VALUES (%s,%s)', (1, 'english-0;welsh-0'))
        self.db.connection.commit()
        ops = '[DATABASE]\n' + ''.join(key + '=' + values[key] + '\n' for key in
                ('DBConn', 'DBName', 'DBusername', 'DBpasswd'))
        # Disposable per-run manager CSRF secret, generated as config/ops.ini.example describes.
        ops += '[VIEW]\nShowProgress=false\nmanagerCsrfSecret=' + binascii.hexlify(os.urandom(32)).decode('ascii') + '\n'
        ops += '[XHIBIT]\nurl=' + self.feed_url + '/page.php?uri=\n'
        ops += '[PROXY]\nproxy=' + self.proxy_url + '/proxy/xhibit_proxy.php\n[CDU]\ncdu=' + self.cdu_url + '/index.php\n'
        ops += '[SOFTWARE]\ncduArchive=' + self.temp + '/cdu.tar\n'
        ops_path = self.write('ops.ini', ops)
        os.mkdir(os.path.join(self.temp, 'debug'))
        cdu_config = self.write('cdu.ini',
                '[PROXY]\nfetch=' + self.proxy_url + '/proxy/xhibit_proxy.php\nrefresh=' + self.proxy_url + '/proxy/xhibit_refresh.php\n'
                'timeout=3\n[HOST]\nmacAddressCmd=printf ' + self.mac + '\n'
                'lastUpdatedLocation=' + self.temp + '/updated.txt\ntimestampMonitorFile=' + self.temp + '/last-run.txt\n'
                '[COMPATIBILITY]\nlegacyDebugDirectory=' + self.temp + '/debug\n'
                '[SCREENSHOT]\nsudo=' + self.temp + '/no-platform-sudo\n')
        password_file = os.path.join(self.temp, 'password')
        subprocess.check_output([shutil.which('htpasswd'), '-bc', password_file, self.user, self.password], stderr=subprocess.STDOUT)
        auth = self.write('auth.conf', 'AuthType Basic\nAuthName "Local test only"\nAuthUserFile "' + password_file + '"\nRequire valid-user\n')
        for role in ('localproxy', 'cdu'):
            package = os.path.join(self.temp, role + '.tar.gz')
            deploy = os.path.join(REPO, 'migration', 'deploy.py')
            flags = ['--with-manager'] if role == 'localproxy' and self.with_manager else []
            subprocess.check_output([sys.executable, deploy, 'package', role, '--python', sys.executable, '--output', package] + flags)
            if role == 'cdu':
                subprocess.check_output([sys.executable, deploy, 'package', role, '--python', sys.executable,
                                         '--format', 'tar', '--output', os.path.join(self.temp, 'cdu.tar')])
            install = os.path.join(self.temp, role)
            os.mkdir(install)
            with tarfile.open(package) as archive:
                for entry in archive.getmembers():
                    destination = os.path.join(install, entry.name)
                    if not entry.isfile() or not os.path.abspath(destination).startswith(install + os.sep):
                        raise ValueError('Unexpected package entry')
                    parent = os.path.dirname(destination)
                    if not os.path.isdir(parent):
                        os.makedirs(parent)
                    with open(destination, 'wb') as stream:
                        stream.write(archive.extractfile(entry).read())
                    os.chmod(destination, entry.mode)
            routes = os.path.join(self.temp, role + '-routes')
            command = [sys.executable, deploy, 'apache', role, '--install-root', install,
                       '--config', ops_path if role == 'localproxy' else cdu_config, '--output', routes]
            if role == 'localproxy' and self.with_manager:
                command += ['--with-manager', '--auth-config', auth]
            subprocess.check_output(command)
            for filename in os.listdir(routes):
                if filename.endswith('.disabled'):
                    os.rename(os.path.join(routes, filename), os.path.join(routes, filename[:-9]))
        httpd = shutil.which('httpd') or shutil.which('apache2')
        modules = next(path for path in ('/usr/libexec/apache2', '/usr/lib64/httpd/modules', '/usr/lib/apache2/modules')
                       if os.path.isfile(os.path.join(path, 'mod_cgi.so')))
        conf = 'ServerRoot "{0}"\nDefaultRuntimeDir "{0}"\nMutex file:{0} default\nPidFile "{0}/httpd.pid"\nErrorLog "{0}/error.log"\n'.format(self.temp)
        for name in ('mpm_prefork','authz_core','authz_host','authz_user','authn_core','authn_file','auth_basic','alias','env','cgi','mime','dir','unixd'):
            path = os.path.join(modules, 'mod_' + name + '.so')
            if os.path.isfile(path):
                conf += 'LoadModule {0}_module "{1}"\n'.format(name, path)
        conf += 'ServerName 127.0.0.1\nUser ' + pwd.getpwuid(os.getuid()).pw_name + '\nGroup ' + grp.getgrgid(os.getgid()).gr_name + '\n'
        conf += 'StartServers 3\nMinSpareServers 2\nMaxSpareServers 5\nServerLimit 8\nMaxRequestWorkers 8\n'
        mime = next(path for path in ('/private/etc/apache2/mime.types','/etc/mime.types','/etc/httpd/conf/mime.types') if os.path.isfile(path))
        conf += 'TypesConfig "' + mime + '"\nPassEnv PYTHONPATH\nSetEnv PYTHONDONTWRITEBYTECODE 1\n'
        for role, url in (('localproxy', self.proxy_url), ('cdu', self.cdu_url)):
            number = urllib.parse.urlparse(url).port
            install = os.path.join(self.temp, role)
            conf += 'Listen 127.0.0.1:{0}\n<VirtualHost 127.0.0.1:{0}>\nDocumentRoot "{1}"\n<Directory "{1}">\nRequire all denied\n</Directory>\nInclude "{2}/{3}-routes/*.conf"\n</VirtualHost>\n'.format(number, install, self.temp, role)
        config = self.write('httpd.conf', conf)
        subprocess.check_output([httpd, '-t', '-f', config], stderr=subprocess.STDOUT)
        self.apache_log = open(os.path.join(self.temp, 'apache-process.log'), 'wb')
        # Apache terminates its worker process group during shutdown. Isolate it
        # from the test runner and any other locally running preview.
        self.apache = subprocess.Popen([httpd, '-DFOREGROUND', '-f', config],
                                       stdout=self.apache_log, stderr=self.apache_log,
                                       start_new_session=True)
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.apache.poll() is not None:
                raise RuntimeError('Apache exited; inspect ' + self.temp)
            try:
                if self.request('proxy', '/proxy/xhibit_proxy.php')[0] == 200:
                    return self
            except IOError:
                pass
            time.sleep(0.05)
        raise RuntimeError('Apache did not become ready; inspect ' + self.temp)

    def request(self, role, path, data=None, authenticated=False):
        target = (self.proxy_url if role == 'proxy' else self.cdu_url) + path
        encoded = urllib.parse.urlencode(data).encode('utf-8') if data is not None else None
        request = urllib.request.Request(target, data=encoded)
        if authenticated:
            token = base64.b64encode((self.user + ':' + self.password).encode('ascii')).decode('ascii')
            request.add_header('Authorization', 'Basic ' + token)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            response = opener.open(request, timeout=15)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.code, response.read(), response.headers

    def stop(self):
        if self.apache is not None:
            self.apache.terminate()
            try:
                self.apache.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.apache.kill()
                self.apache.wait()
            self.apache = None
        if self.apache_log is not None:
            self.apache_log.close()
            self.apache_log = None
        if self.feed is not None:
            self.feed.shutdown()
            self.feed.server_close()
            self.feed = None
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.admin is not None:
            if self.created:
                self.admin.execute('DROP DATABASE ' + self.name)
                self.created = False
            self.admin.close()
            self.admin = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-config', required=True)
    parser.add_argument('--with-manager', action='store_true')
    args = parser.parse_args()
    stack = LocalStack(args.database_config, with_manager=args.with_manager)
    def finish(*unused):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, finish)
    try:
        stack.start()
        print(json.dumps({'proxy': stack.proxy_url + '/manager/', 'cdu': stack.cdu_url + '/index.php',
                          'username': stack.user, 'password': stack.password, 'state': stack.temp,
                          'database': stack.name, 'pid': os.getpid(), 'fixture_data_only': True}, indent=2))
        sys.stdout.flush()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stack.stop()


if __name__ == '__main__':
    main()
