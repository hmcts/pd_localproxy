"""No real SSH, credentials, application endpoints or production files used."""
import base64
import contextlib
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
SCRIPT = os.path.join(MIGRATION, 'compare_github.py')
SPEC = importlib.util.spec_from_file_location('github_comparison', SCRIPT)
if hasattr(importlib.util, 'module_from_spec'):
    compare = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(compare)
else:
    compare = SPEC.loader.load_module()  # Python 3.4 test harness.
COMMIT = 'a' * 40


def baseline(role, sources):
    return dict(repository=compare.REPOSITORIES[role], requested_ref='master', commit=COMMIT,
                commit_url='https://github.com/' + compare.REPOSITORIES[role] + '/commit/' + COMMIT,
                excluded=[], files=[dict(path=path, sha256=compare.digest(data), size=len(data),
                    content_b64=base64.b64encode(data).decode('ascii')) for path, data in sorted(sources.items())])


class GitHubComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix='xhibit-github-test-'))
        self.addCleanup(shutil.rmtree, self.temp)
        self.locations = dict(proxy_root=self.temp + '/proxy', parser_file=self.temp + '/parser/xhibit.py',
                              manager_root=self.temp + '/manager', cdu_root=self.temp + '/cdu',
                              updatescripts_root=self.temp + '/updatescripts')
        for path in [self.locations['proxy_root'], os.path.dirname(self.locations['parser_file']),
                     self.locations['manager_root'], self.locations['cdu_root'], self.locations['updatescripts_root']]:
            os.mkdir(path)

    def fixture(self, path, data):
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        compare.private_write(path, data)

    def payload(self, sources=None, include_diffs=False):
        sources = sources or {'proxy/xhibit.py': b'print("hello")\n', 'manager/index.php': b'<?php echo "Hello"; ?>\n'}
        return dict(baselines={'proxy': baseline('proxy', sources)}, locations=self.locations,
                    include_diffs=include_diffs, extra_roots=[], target='fixture-proxy')

    def install(self, payload):
        for role, source in payload['baselines'].items():
            for item in source['files']:
                path = compare.mapped_path(role, item['path'], payload['locations'])
                if path:
                    self.fixture(path, base64.b64decode(item['content_b64'].encode('ascii')))

    def test_exact_matches_and_parser_mapping(self):
        payload = self.payload()
        self.install(payload)
        result = compare.compare_on_server(payload)
        self.assertEqual([entry['status'] for entry in result['files']], ['identical', 'identical'])
        parser = next(entry for entry in result['files'] if entry['repo_path'] == 'proxy/xhibit.py')
        self.assertEqual(parser['server_path'], self.locations['parser_file'])
        self.assertEqual(compare.summarize(result)['exit_code'], 0)

    def test_changed_missing_extra_and_crlf_distinguished(self):
        payload = self.payload()
        self.fixture(self.locations['parser_file'], b'print("hello")\r\n')
        self.fixture(self.locations['manager_root'] + '/production-only.php', b'<?php echo "extra"; ?>')
        result = compare.compare_on_server(payload)
        statuses = {entry['repo_path']: entry for entry in result['files']}
        self.assertEqual(statuses['manager/index.php']['status'], 'missing')
        self.assertEqual(statuses['proxy/xhibit.py']['status'], 'different')
        self.assertTrue(statuses['proxy/xhibit.py']['equal_after_crlf_normalization'])
        self.assertEqual(result['production_only'][0]['status'], 'production_only')
        self.assertEqual(compare.summarize(result)['exit_code'], 1)

    def test_diffs_are_opt_in_and_redacted_before_context(self):
        original = b'$password = "baseline-canary";\necho "old";\n'
        payload = self.payload({'manager/index.php': original})
        self.fixture(self.locations['manager_root'] + '/index.php', b'$password = "production-canary";\necho "new";\n')
        result = compare.compare_on_server(payload)
        self.assertNotIn('redacted_diff', result['files'][0])
        payload['include_diffs'] = True
        result = compare.compare_on_server(payload)
        diff = result['files'][0]['redacted_diff']
        self.assertNotIn('baseline-canary', diff)
        self.assertNotIn('production-canary', diff)
        self.assertIn('REDACTED', diff)
        self.assertIn('new', diff)

    def test_secret_only_changes_never_report_identical(self):
        payload = self.payload({'manager/index.php': b'$password = "before";\n'}, include_diffs=True)
        self.fixture(self.locations['manager_root'] + '/index.php', b'$password = "after";\n')
        result = compare.compare_on_server(payload)
        self.assertEqual(result['files'][0]['status'], 'different')
        self.assertIn('diff_note', result['files'][0])
        self.assertEqual(compare.summarize(result)['exit_code'], 1)

    def test_data_secrets_and_logs_excluded_from_inventory(self):
        payload = self.payload()
        self.install(payload)
        for name in ['ops.ini', 'case.xml', 'case.html', 'records.sql', 'error.log',
                     'manager.passwd', 'private.key', '.env.production', 'logs/unsafe.php']:
            self.fixture(self.locations['manager_root'] + '/' + name, b'not to be collected')
        result = compare.compare_on_server(payload)
        self.assertEqual(result['production_only'], [])

    def test_binary_assets_hash_only(self):
        payload = self.payload({'manager/images/logo.png': b'\x00one'}, include_diffs=True)
        self.fixture(self.locations['manager_root'] + '/images/logo.png', b'\x00two')
        result = compare.compare_on_server(payload)
        self.assertEqual(result['files'][0]['status'], 'different')
        self.assertNotIn('redacted_diff', result['files'][0])

    def test_unmapped_updaters_fail_incomplete(self):
        payload = self.payload({'updatescripts/Update.sh': b''})
        payload['locations']['updatescripts_root'] = None
        result = compare.compare_on_server(payload)
        self.assertEqual(result['files'][0]['status'], 'unmapped_unchecked')
        self.assertEqual(compare.summarize(result)['exit_code'], 3)

    def test_symlinked_webroot_and_file_are_not_followed(self):
        payload = self.payload()
        real = self.temp + '/real-manager'
        os.mkdir(real)
        os.rmdir(self.locations['manager_root'])
        os.symlink(real, self.locations['manager_root'])
        self.fixture(real + '/index.php', b'private')
        os.symlink(real + '/index.php', self.locations['parser_file'])
        result = compare.compare_on_server(payload)
        self.assertTrue(all(entry['status'] == 'symlink_unchecked' for entry in result['files']))
        self.assertEqual(compare.summarize(result)['exit_code'], 3)

    def test_cdu_mapping_is_separate_and_never_implies_live_cdu(self):
        payload = self.payload()
        payload['baselines'] = {'cdu': baseline('cdu', {'index.php': b'<?php ?>', 'xsl/new/display.xsl': b'<xsl/>'})}
        self.install(payload)
        result = compare.compare_on_server(payload)
        self.assertEqual(compare.summarize(result)['exit_code'], 0)
        self.assertTrue(all(entry['server_path'].startswith(self.locations['cdu_root'] + '/') for entry in result['files']))
        report = compare.build_report(payload, result)
        self.assertIn('NOT proof of behaviour', compare.text_report(report))

    def test_unreadable_file_is_not_a_match(self):
        entry, raw = compare.read_file(self.locations['manager_root'], [0])
        self.assertEqual(entry['status'], 'not_regular')
        path = self.locations['parser_file']
        self.fixture(path, b'content')
        with mock.patch.object(compare.os, 'open', side_effect=PermissionError()):
            entry, raw = compare.read_file(path, [0])
        self.assertEqual(entry['status'], 'unreadable')
        self.assertIsNone(raw)

    def test_size_limits_report_unchecked(self):
        path = self.locations['parser_file']
        self.fixture(path, b'12345')
        with mock.patch.object(compare, 'MAX_FILE', 2):
            entry, raw = compare.read_file(path, [0])
        self.assertEqual(entry['status'], 'size_limit_unchecked')
        self.assertIsNone(raw)

    def test_baseline_rejects_bad_hash_secret_and_traversal(self):
        for path in ['../escape.php', '/escape.php', 'manager/../escape.php', 'manager/ops.ini']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                compare.validate_baseline({'proxy': baseline('proxy', {path: b'payload'})})
        source = baseline('proxy', {'proxy/xhibit.py': b'payload'})
        source['files'][0]['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            compare.validate_baseline({'proxy': source})

    def test_github_archive_is_commit_pinned_and_not_extracted(self):
        archive_bytes = io.BytesIO()
        with tarfile.open(fileobj=archive_bytes, mode='w:gz') as archive:
            for path, data in [('proxy/xhibit.py', b'print("test")'), ('proxy/ops.ini', b'private')]:
                info = tarfile.TarInfo('pd_localproxy-' + COMMIT + '/' + path)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        with mock.patch.object(compare, 'fetch', side_effect=[json.dumps({'sha': COMMIT}).encode('utf-8'), archive_bytes.getvalue()]) as fetch:
            result = compare.github_baseline('proxy', 'release/branch')
        self.assertEqual(result['commit'], COMMIT)
        self.assertIn('release%2Fbranch', fetch.call_args_list[0][0][0])
        self.assertTrue(fetch.call_args_list[1][0][0].endswith('/' + COMMIT))
        self.assertEqual([entry['path'] for entry in result['files']], ['proxy/xhibit.py'])
        self.assertEqual(result['excluded'][0]['path'], 'proxy/ops.ini')

    def test_root_and_host_shell_injection_rejected(self):
        for path in ['/', '/var/www', '/etc', '/app/../etc', '/app\nname']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                compare.validate_root(path)
        args = mock.Mock(host='server;touch marker', port=22)
        with self.assertRaises(ValueError):
            compare.ssh_command(args)

    def test_wire_protocol_executes_helper_in_memory_and_preserves_sources(self):
        payload = self.payload()
        self.install(payload)
        with open(SCRIPT, 'rb') as stream:
            source = stream.read()
        request = base64.b64encode(source) + b'\n' + json.dumps(payload).encode('utf-8')
        bootstrap = 'import sys,base64;exec(base64.b64decode(sys.stdin.buffer.readline()))'
        process = subprocess.Popen([sys.executable, '-B', '-c', bootstrap, '--remote'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(request, timeout=20)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertTrue(stdout.startswith(compare.MARKER.encode('ascii')))
        response = json.loads(stdout[len(compare.MARKER):].decode('utf-8'))
        self.assertEqual(response['report']['summary']['exit_code'], 0)
        self.assertNotIn('content_b64', json.dumps(response))
        self.assertEqual(os.listdir(self.locations['manager_root']), ['index.php'])

    def test_offline_cli_never_contacts_github(self):
        payload = self.payload()
        self.install(payload)
        bundle_path = self.temp + '/baseline.json'
        compare.private_write(bundle_path, json.dumps({'baselines': payload['baselines']}).encode('utf-8'))
        report = compare.build_report(payload, compare.compare_on_server(payload))
        response = dict(report=report, report_text=compare.text_report(report))
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', [SCRIPT, 'compare', '--host', 'fixture', '--only', 'proxy',
                    '--baseline', bundle_path, '--output-parent', self.temp]), \
             mock.patch.object(compare, 'fetch', side_effect=AssertionError('Unexpected internet access')), \
             mock.patch.object(compare, 'run_remote', return_value=response), contextlib.redirect_stdout(output):
            previous = os.umask(0o077)
            try:
                self.assertEqual(compare.main(), 0)
            finally:
                os.umask(previous)
        report_dirs = [name for name in os.listdir(self.temp) if name.startswith('xhibit-github-compare-')]
        self.assertEqual(len(report_dirs), 1)
        report_path = self.temp + '/' + report_dirs[0] + '/report.json'
        self.assertEqual(stat.S_IMODE(os.stat(report_path).st_mode), 0o600)

    def test_ssh_failure_never_produces_match_report(self):
        args = mock.Mock(timeout=10)
        process = mock.Mock(returncode=255)
        process.communicate.return_value = (b'', None)
        with mock.patch.object(compare, 'ssh_command', return_value=['mock-ssh']), \
             mock.patch.object(compare.subprocess, 'Popen', return_value=process), self.assertRaises(ValueError):
            compare.run_remote(args, self.payload())

    @unittest.skipUnless(os.environ.get('XHIBIT_TEST_PWSH'), 'Optional portable development PowerShell not configured')
    def test_powershell_entrypoint_pipeline_with_fake_ssh_and_stubbed_windows_acl(self):
        # This verifies the real native stdin/stdout protocol. No real SSH target.
        # Windows ACL creation must still be verified ON Windows, not simulated here.
        payload = self.payload()
        payload['baselines'] = {'cdu': baseline('cdu', {'index.php': b'<?php echo "fixture"; ?>\n'})}
        self.install(payload)
        bundle = self.temp + '/public-baseline.json'
        self.fixture(bundle, json.dumps({'baselines': payload['baselines']}).encode('utf-8'))
        fake_ssh = self.temp + '/fake-ssh'
        self.fixture(fake_ssh, b'#!/bin/sh\nfor xhibit_arg do xhibit_last="$xhibit_arg"; done\nexec /bin/sh -c "$xhibit_last"\n')
        os.chmod(fake_ssh, 0o700)
        output_dir = self.temp + '/powershell-report'
        os.mkdir(output_dir, 0o700)
        ps_script = self.temp + '/pipeline-test.ps1'
        source_ps = os.path.join(MIGRATION, 'Compare-XhibitGitHub.ps1')
        def ps_quote(value):
            return "'" + value.replace("'", "''") + "'"
        body = '''$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile(SOURCE_PS,[ref]$tokens,[ref]$errors)
if($errors.Count){ throw ($errors | Out-String) }
$source=[IO.File]::ReadAllText(SOURCE_PS)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'New-PrivateOutput'},$true)
$source=$source.Remove($function.Extent.StartOffset,$function.Extent.EndOffset-$function.Extent.StartOffset).Insert($function.Extent.StartOffset, 'function New-PrivateOutput { return OUTPUT_DIR }')
$source=$source.Replace('$PSScriptRoot',MIGRATION_LITERAL)
$block=[ScriptBlock]::Create($source)
& $block -ProxyHost fixture-cdu -Only cdu -BaselineFile BUNDLE -SshExecutable FAKE_SSH -RemotePython REMOTE_PYTHON -CduRoot CDU_ROOT
'''
        replacements = {
            'SOURCE_PS': ps_quote(source_ps), 'OUTPUT_DIR': ps_quote(output_dir).replace("'", "''"),
            'MIGRATION_LITERAL': ps_quote(ps_quote(MIGRATION)), 'BUNDLE': ps_quote(bundle),
            'FAKE_SSH': ps_quote(fake_ssh), 'REMOTE_PYTHON': ps_quote(sys.executable),
            'CDU_ROOT': ps_quote(self.locations['cdu_root'])}
        for key, value in replacements.items():
            body = body.replace(key, value)
        self.fixture(ps_script, body.encode('utf-8'))
        process = subprocess.Popen([os.environ['XHIBIT_TEST_PWSH'], '-NoLogo', '-NoProfile', '-NonInteractive',
                                    '-File', ps_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, stdout.decode('utf-8', 'replace') + stderr.decode('utf-8', 'replace'))
        with open(output_dir + '/report.json') as stream:
            report = json.load(stream)
        self.assertEqual(report['summary']['exit_code'], 0)
        self.assertEqual(report['files'][0]['status'], 'identical')
        self.assertNotIn('content_b64', json.dumps(report))


if __name__ == '__main__':
    unittest.main()
