# -*- coding: utf-8 -*-
"""Opt-in, isolated PHP 5.4 CGI differential tests. Never install PHP on the host.

XHIBIT_PHP_REFERENCE_DIR: private output from prepare_reference.py, outside Git.
XHIBIT_PHP_REFERENCE_IMAGE: prebuilt local test-only image with php-cgi + XSL.
The container has no external network, only a synthetic loopback feed. Its mount
contains copies of legacy code and synthetic inputs, never production config/data.
"""
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from test_compatibility import TempCase, cdu, xml_fixture, http_support, CDU, localproxy, MAC


@unittest.skipUnless(os.environ.get('XHIBIT_PHP_REFERENCE_DIR') and os.environ.get('XHIBIT_PHP_REFERENCE_IMAGE'),
                     'Private legacy PHP reference image/sources not configured')
class PHPReferenceTests(TempCase):
    def setUp(self):
        super(PHPReferenceTests, self).setUp()
        self.container = None
        reference = os.environ['XHIBIT_PHP_REFERENCE_DIR']
        with io.open(os.path.join(reference, 'provenance.json'), encoding='utf-8') as stream:
            manifest = json.load(stream)
        self.app = os.path.join(self.temp, 'cdu')
        shutil.copytree(os.path.join(reference, 'cdu'), self.app)
        if os.path.isdir(os.path.join(reference, 'software')):
            shutil.copytree(os.path.join(reference, 'software'), os.path.join(self.temp, 'software'))
        os.mkdir(os.path.join(self.temp, 'proxy'))
        shutil.copyfile(os.path.join(reference, 'xhibit_proxy.php'), os.path.join(self.temp, 'proxy', 'xhibit_proxy.php'))
        os.mkdir(os.path.join(self.temp, 'bin'))
        for name, digest in manifest['files'].items():
            if name.startswith('cdu/'):
                with open(os.path.join(self.temp, name), 'rb') as stream:
                    self.assertEqual(hashlib.sha256(stream.read()).hexdigest(), digest, name)
        os.mkdir(os.path.join(self.temp, 'feed'))
        self.feed = os.path.join(self.temp, 'feed', 'current.xml')
        self.configure()
        image = os.environ['XHIBIT_PHP_REFERENCE_IMAGE']
        self.container = subprocess.check_output(['docker', 'run', '-d', '--network', 'none',
                '-v', os.path.realpath(self.temp)+':/reference', image,
                'php', '-S', '127.0.0.1:9000', '-t', '/reference/feed']).decode('ascii').strip()
        self.addCleanup(self.stop)
        # Docker exec runs after PHP server startup; verify version, don't assume.
        version = subprocess.check_output(['docker', 'exec', self.container, 'php', '-r', 'echo PHP_VERSION;'])
        self.assertTrue(version.startswith(b'5.4.'), version)

    def stop(self):
        if self.container:
            subprocess.check_output(['docker', 'stop', '-t', '1', self.container], stderr=subprocess.STDOUT)
            subprocess.check_output(['docker', 'rm', self.container], stderr=subprocess.STDOUT)
            self.container = None

    def configure(self, fetch='http://127.0.0.1:9000/current.xml', mac='printf b8:27:eb:67:75:8f'):
        with io.open(os.path.join(self.app, 'cdu.ini'), 'w', encoding='utf-8') as stream:
            stream.write('fetch='+fetch+'\ntimeout=0.1\nmacAddressCmd='+mac+'\n'
                         'lastUpdatedLocation=/reference/updated\ntimestampMonitorFile=/reference/monitor\n')

    def php(self, route, query='', directory='cdu', charset='UTF-8'):
        process = subprocess.Popen(['docker', 'exec', '-w', '/reference/'+directory,
                '-e', 'PATH=/reference/bin:/usr/bin:/bin',
                '-e', 'REDIRECT_STATUS=1', '-e', 'REQUEST_METHOD=GET', '-e', 'SERVER_PROTOCOL=HTTP/1.1',
                '-e', 'SCRIPT_FILENAME=/reference/'+directory+'/'+route, '-e', 'SCRIPT_NAME=/'+route,
                '-e', 'QUERY_STRING='+query, self.container, 'php-cgi',
                '-d', 'display_errors=0', '-d', 'log_errors=1', '-d', 'date.timezone=UTC',
                '-d', 'default_charset='+charset], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raw, errors = process.communicate()
        self.assertIn(process.returncode, (0, 1, 255))
        header, body = raw.split(b'\r\n\r\n', 1)
        headers = dict(line.decode('latin1').split(': ', 1) for line in header.split(b'\r\n'))
        status = int(headers.pop('Status', '200 OK').split()[0])
        headers = {key.lower(): value for key, value in headers.items() if key.lower() != 'x-powered-by'}
        return status, headers, body

    def test_software_downloads_checksums_and_missing_empty_archive(self):
        if not os.path.isdir(os.path.join(self.temp, 'software')):
            self.skipTest('Hash-verified software transcript not supplied to reference preparation')
        path = os.path.join(self.temp, 'software', 'cdu.tar')
        for data in (b'\0\xfftest-package\r\n', b'', None):
            if data is not None:
                with open(path, 'wb') as stream: stream.write(data)
            else:
                os.unlink(path)
            for route in ('checksum.php', 'download.php'):
                for charset in ('', 'UTF-8'):
                    before = self.php(route, directory='software', charset=charset)
                    values = {'cduArchive':path, 'checksumContentType':'text/plain'+(';charset='+charset if charset else '')}
                    after = localproxy.handle(self.request(route), values)
                    self.assertEqual((after.status, dict((key.lower(),value) for key,value in after.headers), after.body), before)

    def test_wrapper_parameters_status_and_exact_xml_bytes(self):
        xml = xml_fixture()
        with open(os.path.join(self.temp, 'proxy.xml'), 'wb') as stream: stream.write(xml)
        stub = os.path.join(self.temp, 'bin', 'parser')
        with io.open(stub, 'w', encoding='utf-8') as stream:
            stream.write('#!/bin/sh\nprintf "%s\\n" "$@" > /reference/args\ncat /reference/proxy.xml\n')
        os.chmod(stub, 0o700)
        with io.open(os.path.join(self.temp, 'proxy', 'proxy.ini'), 'w', encoding='utf-8') as stream:
            stream.write('PARSER_SCRIPT=/reference/bin/parser\nDB_INI_FILE=/reference/ops.ini\n')
        for query, index in [('', None), ('macAddr=invalid', None), ('macAddr='+MAC, None),
                             ('macAddr='+MAC+'&currentPageIndex=12abc&data_refresh=1', 12),
                             ('macAddr='+MAC+'&currentPageIndex=garbage', 0),
                             ('macAddr='+MAC+'&currentPageIndex=-1', -1)]:
            before = self.php('xhibit_proxy.php', query, directory='proxy')
            renderer = mock.Mock(return_value=xml)
            after = localproxy.handle(self.request('xhibit_proxy.php', query), {'opsIniPath':'/reference/ops.ini'}, renderer)
            self.assertEqual((after.status, dict((key.lower(),value) for key,value in after.headers), after.body), before)
            if renderer.called:
                renderer.assert_called_once_with(MAC, '/reference/ops.ini', 0, index, None, timeout=None)
                with io.open(os.path.join(self.temp, 'args'), encoding='utf-8') as stream:
                    args = stream.read().splitlines()
                self.assertEqual(args, [MAC, '/reference/ops.ini', '0'] + ([str(index)] if index is not None else []))

    def test_screenshot_response_failure_and_reference_cleanup(self):
        png = b'\x89PNG\r\n\x1a\ncontrolled fixture'
        sudo = os.path.join(self.temp, 'bin', 'sudo')
        with io.open(sudo, 'w', encoding='utf-8') as stream:
            stream.write('#!/bin/sh\nprintf '+base64.b64encode(png).decode('ascii')+' | base64 -d > "/tmp/$5.png"\n')
        os.chmod(sudo, 0o700)
        before = self.php('screenshot.php')
        after = cdu.screenshot({}, lambda *a, **k:png)
        self.assertEqual((after.status, dict((key.lower(),value) for key,value in after.headers), after.body), before)
        remaining = subprocess.check_output(['docker','exec',self.container,'find','/tmp','-name','*-www-data.png'])
        self.assertEqual(remaining, b'')
        os.unlink(sudo)
        before = self.php('screenshot.php')
        after = cdu.screenshot({}, lambda *a, **k:b'')
        self.assertEqual((after.status, dict((key.lower(),value) for key,value in after.headers), after.body), before)

    def compare_content(self, data, query='', fetch_error=False):
        with open(self.feed, 'wb') as stream: stream.write(data)
        for path in (os.path.join(self.temp,'monitor'), self.settings()['timestampMonitorFile']):
            if os.path.exists(path): os.utime(path, (0,0))
        before = self.php('xhibit_content.php', query)
        settings = self.settings()
        settings['timeout'] = '0.1'
        if 'macAddressCmd' not in settings: settings['macAddressCmd'] = 'printf b8:27:eb:67:75:8f'
        fetcher = mock.Mock(side_effect=IOError('controlled failure')) if fetch_error else mock.Mock(return_value=data)
        after = cdu.handle(self.request('xhibit_content.php', query), settings, fetcher)
        self.assertEqual((after.status, dict((key.lower(), value) for key, value in after.headers), after.body), before)
        self.assertTrue(os.path.isfile(os.path.join(self.temp, 'monitor')))
        self.assertTrue(os.path.isfile(settings['timestampMonitorFile']))
        self.assertGreater(os.stat(os.path.join(self.temp, 'monitor')).st_mtime, 0)
        self.assertGreater(os.stat(settings['timestampMonitorFile']).st_mtime, 0)
        legacy_state = os.path.join(self.temp, 'updated')
        if os.path.exists(legacy_state):
            with open(legacy_state, 'rb') as stream: expected = stream.read()
            with open(settings['lastUpdatedLocation'], 'rb') as stream: self.assertEqual(stream.read(), expected)
        return before[2], after.body

    def test_all_page_types_languages_and_exact_shell_bytes(self):
        before = self.php('index.php')
        self.assertFalse(os.path.exists(os.path.join(self.temp, 'monitor')))
        after = cdu.handle(self.request('index.php'), self.settings())
        self.assertEqual((after.status, after.body), (before[0], before[2]))
        cases = []
        for page in cdu.FULL:
            for language in ('English', 'Welsh'):
                data = xml_fixture(page).replace(b'English', language.encode('ascii'))
                legacy, python = self.compare_content(data, 'currentPageIndex=0')
                cases.append(dict(name=language+' '+page, legacy=base64.b64encode(legacy).decode('ascii'),
                                  python=base64.b64encode(python).decode('ascii')))
        import re
        rows = re.search(b'<COURTCASE>.*?</COURTCASE>', xml_fixture(), re.S).group(0)
        additional = [('English scrolling', xml_fixture().replace(rows, rows * 80)),
                      ('English power saving', xml_fixture().replace(b'DISABLED', b'ENABLED')),
                      ('Welsh power saving', xml_fixture().replace(b'DISABLED', b'ENABLED').replace(b'English', b'Welsh')),
                      ('Unicode notices', xml_fixture().replace(b'A &amp; B', b'Welsh \xc3\xb4 & raw &amp; entity')),
                      ('Empty feed holding', b'')]
        for name, data in additional:
            legacy, python = self.compare_content(data)
            cases.append(dict(name=name, legacy=base64.b64encode(legacy).decode('ascii'),
                              python=base64.b64encode(python).decode('ascii')))
        cases.append(dict(name='AJAX three failures', status=500, legacy='', python=''))
        output = os.environ.get('XHIBIT_BROWSER_CASES')
        if output:
            with io.open(output, 'w', encoding='utf-8') as stream:
                json.dump(cases, stream)
            os.chmod(output, 0o600)

    def test_entities_empty_fields_invalid_xml_and_fallbacks(self):
        for data in [b'', b'not XML', b'<COURT><broken></COURT>', xml_fixture('unknown'),
                     xml_fixture().replace(b'A &amp; B', b'Welsh \xc3\xb4 & raw &amp; existing &#38; numeric'),
                     xml_fixture().replace(b'<XSL>new</XSL>', b'<XSL/>'),
                     xml_fixture().replace(b'<XSL>new</XSL>', b'<XSL>arbitrary</XSL>'),
                     xml_fixture().replace(b'<TYPE>Daily List</TYPE>', b'<TYPE>Daily List</TYPE><TYPE>No Info</TYPE>'),
                     xml_fixture().replace(b'<LAST-UPDATED>22 October 2026</LAST-UPDATED>', b'')]:
            self.compare_content(data)
        self.configure(fetch='http://127.0.0.1:1/offline')
        self.compare_content(b'', fetch_error=True)
        # Synthetic test-only upstream; never included in a release/reference source tree.
        with open(os.path.join(self.temp, 'feed', 'slow.php'), 'wb') as stream:
            stream.write(b'<?php usleep(500000); readfile("current.xml"); ?>')
        self.configure(fetch='http://127.0.0.1:9000/slow.php')
        self.compare_content(b'', fetch_error=True)

    def test_mac_command_parameters_and_zero_fallback_match_actual_php(self):
        data = xml_fixture()
        self.configure(mac="printf 'aa:bb:cc:\\n dd:ee:ff\\t\\n'")
        self.compare_content(data, 'macAddr=&currentPageIndex=garbage')
        # Observe the actual requested URL from PHP's synthetic feed log.
        self.php('xhibit_content.php', '')
        logs = subprocess.check_output(['docker', 'logs', self.container], stderr=subprocess.STDOUT)
        self.assertIn(b'macAddr=aa%3Abb%3Acc%3A+dd%3Aee%3Aff', logs)
        self.php('xhibit_content.php', 'macAddr=&currentPageIndex=garbage')
        logs = subprocess.check_output(['docker', 'logs', self.container], stderr=subprocess.STDOUT)
        self.assertIn(b'macAddr=00%3A00%3A00%3A00%3A00%3A00&currentPageIndex=garbage', logs)
        self.configure(mac='printf b8:27:eb:67:75:8f; exit 1')
        self.php('xhibit_content.php')
        logs = subprocess.check_output(['docker', 'logs', self.container], stderr=subprocess.STDOUT)
        self.assertIn(b'macAddr=b8%3A27%3Aeb%3A67%3A75%3A8f', logs)
