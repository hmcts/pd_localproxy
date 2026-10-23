"""Production evidence collection tested ONLY against disposable local fixtures."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

MIGRATION = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location('evidence_collector', os.path.join(MIGRATION, 'collect_production.py'))
if hasattr(importlib.util, 'module_from_spec'):
    collector = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(collector)
else:
    collector = SPEC.loader.load_module()  # Python 3.4 test harness, not application code.


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix='xhibit-collection-test-')
        self.addCleanup(shutil.rmtree, self.temp)
        self.source = os.path.join(self.temp, 'source')
        self.output = os.path.join(self.temp, 'evidence')
        os.mkdir(self.source, 0o700)
        os.mkdir(self.output, 0o700)

    def fixture(self, name, data):
        path = os.path.join(self.source, name)
        collector.private_write(path, data)
        return path

    def test_redacts_common_secrets(self):
        examples = [
            'DBpasswd = "canary-secret"',
            'DBusername=canary-secret',
            '$DBpasswd = "canary-secret";',
            "define('DBpassword', 'canary-secret');",
            "config['password'] = 'canary-secret'",
            'https://user:canary-secret@internal/path',
            '<Resource password="canary-secret" />',
            '<password>canary-secret</password>',
            'Authorization: Bearer canary-secret',
            'SetEnv DB_PASSWORD canary-secret',
            'AuthLDAPBindPassword canary-secret',
            'mysql --password=canary-secret',
            'Cookie: session=canary-secret',
            '-----BEGIN RSA PRIVATE KEY-----\ncanary-secret\n-----END RSA PRIVATE KEY-----']
        for example in examples:
            with self.subTest(example=example):
                result, count = collector.redact(example)
                self.assertNotIn('canary-secret', result)
                self.assertGreater(count, 0)

    def test_nonsecret_config_preserved_byte_for_byte(self):
        source = b'Alias /manager /var/www/lan/manager\r\nListen 192.168.1.254:80\r\n'
        path = self.fixture('localproxy.conf', source)
        scan = collector.Collector(self.output)
        scan.file(path)
        with open(os.path.join(self.output, scan.files[0]['archive_path']), 'rb') as stream:
            self.assertEqual(stream.read(), source)
        with open(path, 'rb') as stream:
            self.assertEqual(stream.read(), source)

    def test_redacted_source_has_original_and_collected_hashes(self):
        original = b'DBpasswd = "canary-secret"\n'
        path = self.fixture('ops.ini', original)
        scan = collector.Collector(self.output)
        scan.file(path)
        entry = scan.files[0]
        self.assertEqual(entry['sha256_original'], hashlib.sha256(original).hexdigest())
        self.assertNotEqual(entry['sha256_original'], entry['sha256_collected'])
        copied = os.path.join(self.output, entry['archive_path'])
        self.assertEqual(stat.S_IMODE(os.stat(copied).st_mode), 0o600)
        with open(copied, 'rb') as stream:
            self.assertNotIn(b'canary-secret', stream.read())

    def test_data_binary_and_password_files_not_copied(self):
        for name in ['court.html', 'feed.xml', 'data.sql', 'error.log', 'manager.passwd', 'private.pem']:
            self.fixture(name, b'private contents')
        self.fixture('program.py', b'print("hello")\n')
        scan = collector.Collector(self.output)
        scan.tree(self.source)
        self.assertEqual([os.path.basename(e['path']) for e in scan.files if e['content_copied']], ['program.py'])
        for entry in scan.files:
            if os.path.basename(entry['path']) in ('manager.passwd', 'private.pem'):
                self.assertNotIn('sha256_original', entry)

    def test_manifest_only_does_not_copy_source(self):
        self.fixture('program.py', b'print("hello")\n')
        scan = collector.Collector(self.output, manifest_only=True)
        scan.tree(self.source)
        self.assertIn('sha256_original', scan.files[0])
        self.assertFalse(scan.files[0]['content_copied'])
        self.assertEqual(os.listdir(self.output), [])

    def test_symlinks_and_excluded_directories_not_followed(self):
        path = self.fixture('program.py', b'print("hello")\n')
        os.symlink(path, os.path.join(self.source, 'link.py'))
        os.symlink(self.output, os.path.join(self.source, 'linked-directory'))
        self.fixture('logs/secret.py', b'not collected')
        scan = collector.Collector(self.output)
        scan.tree(self.source)
        self.assertEqual(len(scan.files), 3)
        self.assertEqual(sum(e.get('kind') == 'symlink' for e in scan.files), 2)
        self.assertEqual(sum(e['content_copied'] for e in scan.files), 1)

    def test_limits_and_missing_roots_are_reported(self):
        self.fixture('one.py', b'12345')
        self.fixture('two.py', b'12345')
        scan = collector.Collector(self.output, limit=1)
        scan.tree(self.source)
        self.assertTrue(any('File-count limit' in issue for issue in scan.issues))
        scan.tree(os.path.join(self.temp, 'missing'))
        self.assertTrue(any('Missing requested path' in issue for issue in scan.issues))
        scan = collector.Collector(self.output, byte_limit=1)
        scan.tree(self.source)
        self.assertTrue(any('Aggregate read limit' in issue for issue in scan.issues))
        self.assertFalse(any(e['content_copied'] for e in scan.files))

    def test_private_writer_wont_overwrite(self):
        path = self.fixture('same.py', b'original')
        with self.assertRaises(OSError):
            collector.private_write(path, b'replacement')
        with open(path, 'rb') as stream:
            self.assertEqual(stream.read(), b'original')

    def test_cli_archive_smoke_with_no_system_collection(self):
        self.fixture('program.py', b'print("hello")\n')
        output = io.StringIO()
        # All paths and external probes mocked: no production or real host config.
        with mock.patch.object(collector, 'ROOTS', {'proxy': [self.source]}), \
             mock.patch.object(collector, 'COMMON_CONFIG', []), \
             mock.patch.object(collector, 'CONFIG_ROOTS', []), \
             mock.patch.object(collector, 'SCHEDULER_ROOTS', []), \
             mock.patch.object(collector, 'SCHEDULER_FILES', []), \
             mock.patch.object(collector, 'command', return_value={'mock_probe': True}), \
             mock.patch.object(sys, 'argv', ['collector', '--role', 'proxy', '--output-parent', self.temp]), \
             contextlib.redirect_stdout(output):
            previous_umask = os.umask(0o077)
            try:
                self.assertEqual(collector.main(), 0)
            finally:
                os.umask(previous_umask)
        paths = json.loads(output.getvalue())
        self.assertEqual(paths['incomplete'], 0)
        self.assertEqual(stat.S_IMODE(os.stat(paths['archive']).st_mode), 0o600)
        with tarfile.open(paths['archive']) as archive:
            self.assertTrue(any(name.endswith('/manifest.json') for name in archive.getnames()))
        with open(paths['archive'], 'rb') as stream:
            digest = hashlib.sha256(stream.read()).hexdigest()
        with open(paths['checksum']) as stream:
            self.assertEqual(stream.read().split()[0], digest)

    def test_schema_script_with_fake_client_only(self):
        tools_dir = os.path.join(self.temp, 'tools')
        os.mkdir(tools_dir)
        result_dir = os.path.join(self.temp, 'schema-result')
        os.mkdir(result_dir)
        scripts = {
            'mktemp': '#!/bin/sh\nprintf "%s\\n" "$XHIBIT_FAKE_RESULT"\n',
            'mysql': '#!/bin/sh\nprintf "%s\\n" "$@"\n/bin/cat\n'}
        for name, body in scripts.items():
            path = os.path.join(tools_dir, name)
            collector.private_write(path, body.encode('utf-8'))
            os.chmod(path, 0o700)
        env = dict(os.environ, PATH=tools_dir + ':/usr/bin:/bin', XHIBIT_FAKE_RESULT=result_dir)
        script = os.path.join(MIGRATION, 'collect_schema.sh')
        process = subprocess.Popen(['/bin/bash', script, 'fixture_db', 'fixture_user'], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, stderr)
        with open(os.path.join(result_dir, 'schema-metadata.txt')) as stream:
            result = stream.read()
        self.assertTrue(result.startswith('--no-defaults\n'))
        self.assertIn('--password\n', result)
        self.assertIn('information_schema.COLUMNS', result)
        self.assertNotIn('SELECT *', result)
        self.assertNotIn('mysqldump', result)
