"""Metadata collection cannot export database credentials or application records."""
import os
import sys
import unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import compare_github as compare


class TargetedEvidenceTests(unittest.TestCase):
    def test_config_export_is_an_allowlist_and_never_exports_shell_or_secrets(self):
        raw = (b'DBConn=mysql:host=localhost\nDBName=test\nDBusername=secret-user\nDBpasswd=secret-password\n'
               b'fetch=http://user:pass@internal/proxy?secret=hidden\ntimeout=3\n'
               b'macAddressCmd=some-command --credential hidden-value\notherKey=another-secret\n')
        locations = {'proxy_root':'/var/www/proxy', 'parser_file':'/var/www/code/xhibit.py', 'cdu_root':'/var/www/cdu'}
        def read(path, budget):
            if path.endswith('.ini'): return {'status':'read','server_path':path}, raw
            return {'status':'missing'}, None
        with mock.patch.object(compare,'read_file', side_effect=read), mock.patch.object(compare,'schema_metadata', return_value={}), mock.patch('compare_github.os.path.isdir',return_value=False):
            import json
            output = json.dumps(compare.targeted_evidence(locations))
        for value in ('secret-user','secret-password','hidden-value','another-secret','?secret=hidden','user:pass'):
            self.assertNotIn(value, output)
        self.assertIn('timeout', output)

    def test_schema_queries_only_information_schema_and_never_default_values_or_records(self):
        import pymysql
        cursor = mock.Mock()
        cursor.fetchall.return_value = []
        connection = mock.Mock()
        connection.cursor.return_value = cursor
        values = dict(DBConn='mysql:host=localhost', DBName='test', DBusername='private-user', DBpasswd='private-password')
        with mock.patch.object(pymysql,'connect',return_value=connection):
            self.assertEqual(compare.schema_metadata(values), {'columns':[], 'indexes':[], 'tables':[]})
        self.assertEqual(cursor.execute.call_count,3)
        for call in cursor.execute.call_args_list:
            sql, args = call[0]
            self.assertIn('FROM information_schema.', sql)
            self.assertNotIn('COLUMN_DEFAULT', sql)
            self.assertEqual(args, ('test',))
        self.assertTrue(connection.close.called)
        values['DBConn']='mysql:host=external-server'
        with mock.patch.object(pymysql,'connect') as connect, self.assertRaises(ValueError):
            compare.schema_metadata(values)
        self.assertFalse(connect.called)
