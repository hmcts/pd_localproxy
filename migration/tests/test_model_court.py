# -*- coding: utf-8 -*-
"""Model Court provenance, fixed-artifact delivery and opt-in manager boundaries."""
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
from unittest import mock
from test_compatibility import TempCase, LP, CDU, localproxy, MAC


class ModelCourtTests(TempCase):
    def test_verified_assets_are_byte_identical_and_old_profile_is_absent(self):
        with io.open(os.path.join(CDU, 'MODEL_COURT_PROVENANCE.json'), encoding='utf-8') as stream:
            provenance = json.load(stream)
        for source, expected in provenance['files'].items():
            if not source.startswith('cdu/') or source in ('cdu/screenshot.php', 'cdu/xhibit_content.php'):
                continue
            target = source[4:] if source != 'cdu/index.php' else 'python/templates/index.html'
            with open(os.path.join(CDU, target), 'rb') as stream:
                self.assertEqual(hashlib.sha256(stream.read()).hexdigest(), expected, source)
        self.assertEqual(len(os.listdir(os.path.join(CDU, 'xsl', 'new'))), 9)
        for path in ('jquery.min.js', 'bigtext.js', 'cdu.ini', 'xsl/old'):
            self.assertFalse(os.path.exists(os.path.join(CDU, path)), path)

    def test_software_contract_for_binary_empty_missing_and_fixed_filename(self):
        path = os.path.join(self.temp, 'cdu.tar')
        settings = {'cduArchive':path}
        for data in (b'\x00\xffsynthetic package\r\n', b''):
            with open(path, 'wb') as stream: stream.write(data)
            downloaded = localproxy.handle(self.request('download.php', 'file=/etc/passwd'), settings)
            checksum = localproxy.handle(self.request('checksum.php'), settings)
            self.assertEqual((downloaded.status, downloaded.body), (200, data))
            self.assertEqual(downloaded.headers, [('Content-Type','application/octet-stream')])
            self.assertEqual(checksum.body, hashlib.sha1(data).hexdigest().encode('ascii'))
            self.assertEqual(checksum.headers, [('Content-Type','text/plain')])
        os.unlink(path)
        for route in ('download.php', 'checksum.php'):
            response = localproxy.handle(self.request(route), settings)
            self.assertEqual((response.status, response.body), (200, b''))

    def test_default_package_routes_and_optional_manager(self):
        deploy = os.path.join(LP, 'migration', 'deploy.py')
        for enabled in (False, True):
            flags = ['--with-manager'] if enabled else []
            archive = os.path.join(self.temp, str(enabled)+'.tar.gz')
            subprocess.check_output([sys.executable, deploy, 'package', 'localproxy',
                                     '--python', sys.executable, '--output', archive]+flags)
            with tarfile.open(archive) as bundle:
                self.assertEqual('python/manager.py' in bundle.getnames(), enabled)
                self.assertEqual(any(name.startswith('manager/') for name in bundle.getnames()), enabled)
            output = os.path.join(self.temp, 'routes-'+str(enabled))
            subprocess.check_output([sys.executable, deploy, 'apache', 'localproxy', '--install-root', '/opt/xhibit',
                                     '--config', '/etc/xhibit/ops.ini', '--output', output] + flags +
                                    (['--auth-config', '/etc/httpd/manager-auth.conf'] if enabled else []))
            with io.open(os.path.join(output, '00-common.conf'), encoding='utf-8') as stream:
                self.assertEqual('SetEnv XHIBIT_WITH_MANAGER 1' in stream.read(), enabled)
            self.assertEqual(any('manager' in name for name in os.listdir(output)), enabled)
            self.assertFalse(any('refresh' in name for name in os.listdir(output)))
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch('manager.handle') as handler:
            self.assertEqual(localproxy.handle(self.request('index.php'), {'opsIniPath':'unused'}).status, 404)
            self.assertFalse(handler.called)
        with mock.patch.dict(os.environ, {'XHIBIT_WITH_MANAGER':'1'}), mock.patch('manager.handle') as handler:
            localproxy.handle(self.request('index.php', user='operator'), {'opsIniPath':'unused'})
            self.assertTrue(handler.called)

    def test_uncompressed_python_only_download_matches_configured_package(self):
        path = os.path.join(self.temp, 'cdu.tar')
        subprocess.check_output([sys.executable, os.path.join(LP,'migration','deploy.py'), 'package', 'cdu',
                                 '--python', '/usr/bin/python3', '--format', 'tar', '--output', path])
        with open(path, 'rb') as stream: expected = stream.read()
        with tarfile.open(path, 'r:') as bundle:
            self.assertIn('python/cdu.py', bundle.getnames())
            for entry in bundle:
                self.assertFalse(entry.mode & 0o022)
                self.assertFalse(entry.name.endswith(('.php','.ini','.zip','.tar','.gz')))
                self.assertNotIn(b'<?php', bundle.extractfile(entry).read())
        response = localproxy.handle(self.request('download.php'), {'cduArchive':path})
        self.assertEqual(response.body, expected)
