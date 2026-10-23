# -*- coding: utf-8 -*-
"""Opt-in end-to-end Apache, MariaDB, HTML-feed and CDU transformation tests."""
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from local_stack import LocalStack


@unittest.skipUnless(os.environ.get('XHIBIT_TEST_MYSQL_CONFIG'),
                     'Dedicated loopback MySQL/MariaDB test service not configured')
class HTTPStackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = LocalStack(os.environ['XHIBIT_TEST_MYSQL_CONFIG'], with_manager=True)
        try:
            cls.stack.start()
        except Exception:
            cls.stack.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.stack.stop()

    def setUp(self):
        self.stack.db.connection.commit()
        self.stack.db.execute('UPDATE CDU SET title=%s,notification=NULL,url=%s WHERE id=1',
                              ('Local Test Screen', 'english-0;welsh-0'))
        self.mapping('english-0;welsh-0')

    def mapping(self, value):
        self.stack.db.execute('UPDATE urlMappings SET url=%s WHERE cduID=1', (value,))
        self.stack.db.connection.commit()

    def request(self, role, path, data=None, authenticated=False):
        return self.stack.request(role, path, data, authenticated)

    def proxy(self, extra=''):
        return self.request('proxy', '/proxy/xhibit_proxy.php?macAddr=' + self.stack.mac + extra)

    def test_all_proxy_page_types_in_both_languages_over_real_http(self):
        types = ['Daily List', 'Court Detail', 'All Case Status', 'Summary by Name',
                 'Court List', 'All Court Status', 'Jury Current Status', 'No Info']
        for language in ('english', 'welsh'):
            for index, page_type in enumerate(types):
                self.mapping(language + '-' + str(index))
                status, body, headers = self.proxy()
                self.assertEqual(status, 200, (language, page_type, body))
                self.assertEqual(headers.get_content_type(), 'application/xml')
                document = ET.fromstring(body)
                self.assertEqual(document.findtext('PAGE/TYPE'), page_type)
                if page_type != 'No Info':
                    self.assertEqual(document.findtext('PAGE/LANGUAGE'), language.title())
                self.assertEqual(document.findtext('CDU/TITLE'), 'TESTDISPL01')
                self.assertEqual(document.findtext('CDU/MAC-ADDR'), self.stack.mac.upper())
                full_status, full_body, unused = self.request('cdu', '/xhibit_content.php')
                self.assertEqual(full_status, 200, (language, page_type))
                self.assertIn(b'<html', full_body)

    def test_shell_ajax_content_and_state_files_use_live_proxy(self):
        self.mapping('english-0')
        status, shell, headers = self.request('cdu', '/index.php')
        self.assertEqual(status, 200)
        self.assertIn(b"nextPage('xhibit_content.php')", shell)
        self.assertEqual(self.request('cdu', '/')[1], shell)
        status, body, headers = self.request('cdu', '/xhibit_content.php?currentPageIndex=0')
        self.assertEqual(status, 200)
        self.assertIn(b'Local Test Court', body)
        self.assertIn(b'<tr', body)
        with open(os.path.join(self.stack.temp, 'updated.txt'),'rb') as stream:
            self.assertEqual(stream.read(), b'Last Updated: 22 October 2026')
        self.assertTrue(os.path.isfile(os.path.join(self.stack.temp, 'last-run.txt')))

    def test_rotation_and_ignored_http_data_refresh_match_legacy(self):
        first = ET.fromstring(self.proxy()[1])
        self.assertEqual(first.findtext('PAGE/CURRENT-PAGE-INDEX'), '0')
        second = ET.fromstring(self.proxy('&currentPageIndex=0&data_refresh=1')[1])
        self.assertEqual(second.findtext('PAGE/CURRENT-PAGE-INDEX'), '1')
        self.assertEqual(second.findtext('PAGE/LANGUAGE'), 'Welsh')
        wrapped = ET.fromstring(self.proxy('&currentPageIndex=1')[1])
        self.assertEqual(wrapped.findtext('PAGE/CURRENT-PAGE-INDEX'), '0')

    def test_manager_authenticated_views_posts_and_database_audit(self):
        self.assertEqual(self.request('proxy', '/manager/')[0], 401)
        for path, expected in (('/manager/', b'Local Test Screen'),
                               ('/manager/site.php?id=1', b'Local Test Court'),
                               ('/manager/cdu.php?id=1', b'Local Test Screen')):
            status, body, headers = self.request('proxy', path, authenticated=True)
            self.assertEqual(status, 200)
            self.assertIn(expected, body)
        values = dict(id='1', UpdateCDU='Update', title='Updated Screen', description='Test description',
                      location='Reception', macAddress=self.stack.mac, refresh='15', xsl='new', url='manager-only-url')
        status, body, headers = self.request('proxy', '/manager/cdu.php', values, True)
        self.assertEqual(status, 200)
        self.assertIsNone(headers.get('Location'))
        self.stack.db.connection.commit()
        row = self.stack.db.cdu(1)
        self.assertEqual((row['title'], row['url']), ('Updated Screen', 'manager-only-url'))
        self.assertEqual(self.stack.db.parser_row(self.stack.mac)['url'], 'english-0;welsh-0')
        for action, expected in (('UpdateNotice', 'Local test notice'), ('CancelNotice', None)):
            status, body, headers = self.request('proxy', '/manager/cdu.php',
                    dict(id='1', notification='Local test notice', **{action: '1'}), True)
            self.assertEqual(status, 200)
            self.stack.db.connection.commit()
            self.assertEqual(self.stack.db.cdu(1)['notification'], expected)
        audit = self.stack.db.query('SELECT username,eventType FROM AUDIT WHERE eventType=%s', ('UPDATE_CDU',))
        self.assertTrue(audit)
        self.assertEqual(audit[-1]['username'], self.stack.user)

    def test_manager_site_post_persists_without_redirect(self):
        values = dict(id='1', UpdateSite='Update', title='Local Test Court', xsl='new', alert='Pilot alert',
                      selectorURL=self.stack.feed_url + '/selector.php',
                      pageURL=self.stack.feed_url + '/page.php?', powersaveSchedule='[]')
        status, body, headers = self.request('proxy', '/manager/site.php', values, True)
        self.assertEqual(status, 200)
        self.assertIsNone(headers.get('Location'))
        self.stack.db.connection.commit()
        self.assertEqual(self.stack.db.site(1)['alert'], 'Pilot alert')

    def test_holding_pages_denials_and_platform_screenshot_failure(self):
        status, body, headers = self.request('proxy', '/proxy/xhibit_proxy.php?macAddr=invalid')
        self.assertEqual((status, body), (200, b''))
        status, body, headers = self.request('cdu', '/xhibit_content.php?macAddr=invalid')
        self.assertEqual(status, 200)
        self.assertIn(b'No Information', body)
        self.assertIn(self.request('cdu', '/data_refresh.php?macAddr=invalid')[0], (403, 404))
        for role, path in (('proxy', '/python/manager.py'), ('proxy', '/arbitrary.php'),
                           ('cdu', '/python/cdu.py'), ('cdu', '/arbitrary.php')):
            self.assertIn(self.request(role, path)[0], (403, 404))
        # No host sudo account or screenshot capture is used in this local stack.
        self.assertEqual(self.request('cdu', '/screenshot.php')[:2], (200, b''))
        self.mapping('english-7')
        # The verified No Info stylesheet now renders successfully.
        self.assertEqual(self.request('cdu', '/xhibit_content.php')[0], 200)

    def test_cdu_browser_assets_are_public_but_python_is_not(self):
        for path in ('/display_documentNEW.js', '/jquery-3.1.1.min.js', '/onscreen-clock.js', '/localError.html',
                     '/css/new/general.css', '/images/MoJLogo.png'):
            status, body, headers = self.request('cdu', path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body, path)
        self.assertIn(self.request('cdu', '/python/cdu.py')[0], (403, 404))

    def test_software_aliases_download_the_actual_python_only_artifact(self):
        import hashlib
        with open(os.path.join(self.stack.temp, 'cdu.tar'), 'rb') as stream: data = stream.read()
        status, body, headers = self.request('proxy', '/software/download.php?filename=/etc/passwd')
        self.assertEqual((status, body), (200, data))
        self.assertEqual(headers.get_content_type(), 'application/octet-stream')
        status, body, headers = self.request('proxy', '/software/checksum.php')
        self.assertEqual((status, body), (200, hashlib.sha1(data).hexdigest().encode('ascii')))
        self.assertEqual(headers.get_content_type(), 'text/plain')


@unittest.skipUnless(os.environ.get('XHIBIT_TEST_MYSQL_CONFIG'), 'Dedicated loopback test DB not configured')
class DefaultProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = LocalStack(os.environ['XHIBIT_TEST_MYSQL_CONFIG'])
        try: cls.stack.start()
        except Exception:
            cls.stack.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.stack.stop()

    def test_default_manager_is_absent_even_with_credentials(self):
        for path in ('/manager/', '/manager/index.php', '/manager/css/bootstrap.min.css'):
            self.assertIn(self.stack.request('proxy', path, authenticated=True)[0], (403, 404))
        self.assertEqual(self.stack.request('cdu', '/xhibit_content.php')[0], 200)

    def test_default_proxy_preflight_does_not_require_manager_auth(self):
        import subprocess
        deploy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'deploy.py')
        report = subprocess.check_output([sys.executable, deploy, 'preflight', 'localproxy',
                '--install-root', os.path.join(self.stack.temp, 'localproxy'),
                '--config', os.path.join(self.stack.temp, 'ops.ini')])
        self.assertEqual(json.loads(report.decode('utf-8'))['failures'], [])


if __name__ == '__main__':
    unittest.main()
