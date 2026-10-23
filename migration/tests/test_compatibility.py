# -*- coding: utf-8 -*-
"""Characterization and security-boundary tests. Run with unittest discover."""
import ast
import configparser
import contextlib
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
LP = os.path.join(ROOT, 'pd_localproxy')
CDU = os.path.join(ROOT, 'pd_cdu')
sys.path.insert(0, os.path.join(LP, 'python'))
sys.path.insert(0, os.path.join(LP, 'proxy'))
sys.path.insert(0, os.path.join(CDU, 'python'))
import http_support
import localproxy
import manager
import cdu
from database import Database

MAC = 'b8:27:eb:67:75:8f'
ROW = dict(title='Court 1', location='Reception', notification='Notice', macAddress=MAC,
           url='one;two', refresh=15, site='Test Court', pageUrl='http://internal/page.php?',
           powersaveSchedule='[]', welshTitle='Llys Prawf')
TITLES = ['Public Display: Daily List', 'Public Display: Court 1 Detail',
          'Public Display: All Case Status', 'Public Display: Summary By Name',
          'Public Display: Court 1 List', 'Public Display: All Court Status',
          'Public Display: Jury Current Status', 'No Info']
WELSH_TITLES = ['Public Display: Rhestr Ddyddiol', 'Public Display: Llys 1 Manylion ',
                'Public Display: Statws Pob Achos', 'Public Display: Crynodeb yn ôl Enw',
                'Public Display: Llys 1 Rhestr', 'Public Display: Statws Pob Llys',
                'Public Display: Statws Gyfredol - Rheithgor', 'No Info']


def html_page(title, welsh=False):
    timestamp = 'Diweddarwyd Ddiwethaf: ' if welsh else 'Last updated: '
    cells = [('court-room-name','Court 1'), ('case-number','T123*'), ('judge','Judge A'),
             ('hearing-description','Trial'), ('hearing-progress','In progress'),
             ('live-status','Sitting'), ('not-before-time','10:00'), ('defendant-name','Person A'),
             ('case-title','Case title'), ('case-progress-time','10:05'),
             ('case-progress-status','In progress'), ('public-notice','Notice')]
    body = ''.join('<td class="{0}">{1}</td>'.format(*cell) for cell in cells)
    body += '<td><span class="case-number">T123*</span><span class="case-title">Case title</span></td>'
    body += ''.join('<td><div class="{0}">Person A</div></td>'.format(cls) for cls in
                    ['defendant-name-restricted-size350','defendant-name-restricted-size-250',
                     'defendant-name-restricted-size','moved-highlight'])
    noinfo = '<div class="no-information">No information</div>' if title == 'No Info' else ''
    return ('<html><head><title>{0}</title></head><body><table><tr>'
            '<td class="last-updated-date">{1}22 October 2026</td></tr></table>'
            '<table class="results non-scrolling-results"><tbody><tr>{2}</tr></tbody></table>{3}'
            '</body></html>').format(title, timestamp, body, noinfo).encode('utf-8')


def xml_fixture(page='Daily List', xsl='new'):
    return ('''<?xml version="1.0" encoding="UTF-8"?>
<COURT><CDU><VERSION>p3.0</VERSION><SITE-TITLE>Test Court</SITE-TITLE>
<SITE-TITLE-WELSH>Llys Prawf</SITE-TITLE-WELSH><TITLE>Screen</TITLE><LOCATION>Room 1</LOCATION>
<MAC-ADDR>B8:27:EB:67:75:8F</MAC-ADDR><NOTICE>A &amp; B</NOTICE>
<POWER-SAVING>DISABLED</POWER-SAVING><REFRESH>15</REFRESH><URL>one;two</URL><XSL>{0}</XSL></CDU>
<PAGE><LANGUAGE>English</LANGUAGE><LAST-UPDATED>22 October 2026</LAST-UPDATED>
<CURRENT-PAGE-INDEX>0</CURRENT-PAGE-INDEX><CURRENT-URL>one;two</CURRENT-URL><TYPE>{1}</TYPE></PAGE>
<TABLE><COURTCASE><ROOM>Court 1</ROOM><CASENO>T123</CASENO><NAME>Judge A</NAME><TYPE>Trial</TYPE>
<DEFENDANT>Person A</DEFENDANT><DEFENDANTS><DEFENDANT>Person A</DEFENDANT></DEFENDANTS>
<REPORTRESTRICTIONS>TRUE</REPORTRESTRICTIONS><STATUS>Sitting</STATUS><NOTBEFORE>10:00</NOTBEFORE>
</COURTCASE></TABLE><ROOM><DETAIL><JUDGE>Judge A</JUDGE><CASENO>T123</CASENO><TYPE>Trial</TYPE>
<DEFENDANTS><DEFENDANT>Person A</DEFENDANT></DEFENDANTS><NOTICES><NOTICE>Notice</NOTICE></NOTICES>
</DETAIL></ROOM></COURT>''').format(xsl, page).encode('utf-8')


class TempCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix='xhibit-test-')
        self.addCleanup(shutil.rmtree, self.temp)

    def settings(self):
        return dict(fetch='http://internal/proxy/xhibit_proxy.php',
                    refresh='http://internal/proxy/xhibit_refresh.php', timeout='3',
                    macAddressCmd='printf '+MAC,
                    timestampMonitorFile=os.path.join(self.temp, 'lastRun.txt'),
                    lastUpdatedLocation=os.path.join(self.temp, 'lastupdated.txt'),
                    legacyDebugDirectory=self.temp)

    def request(self, route, query='', post=None, user=None):
        env = dict(SCRIPT_NAME=route, QUERY_STRING=query, REQUEST_METHOD='GET')
        body = b''
        if post is not None:
            env.update(REQUEST_METHOD='POST', CONTENT_TYPE='application/x-www-form-urlencoded')
            body = http_support.urllib.parse.urlencode(post).encode('utf-8')
        if user:
            env['REMOTE_USER'] = user
        return http_support.Request(env, body)


class RequestTests(TempCase):
    def test_php_duplicate_and_blank_parameters(self):
        self.assertEqual(http_support.parameters('id=1&id=2&empty='), {'id':'2','empty':''})
        for value, expected in [('garbage',0), ('12suffix',12), ('-2',-2), ('',0), ('  +7',7)]:
            self.assertEqual(http_support.php_int(value), expected)

    def test_config_raw_percent_and_quoted_values(self):
        path = os.path.join(self.temp, 'config.ini')
        with io.open(path, 'w', encoding='utf-8') as stream:
            stream.write('[DATABASE]\nDBpasswd = "a%password"\n[HOST]\ntimeout = 3\n')
        self.assertEqual(http_support.read_ini(path)['DBpasswd'], 'a%password')

    def test_response_bytes_and_204(self):
        stream = io.BytesIO()
        http_support.Response('Welsh ô', content_type='application/xml').emit(stream)
        self.assertEqual(stream.getvalue(), b'Content-Type: application/xml\r\n\r\nWelsh \xc3\xb4')
        stream = io.BytesIO()
        http_support.Response('hidden', status=204).emit(stream)
        self.assertTrue(stream.getvalue().endswith(b'\r\n\r\n'))

    def test_state_writer_keeps_existing_modes_links_and_restricted_directory(self):
        path=os.path.join(self.temp,'updated.txt')
        with open(path,'wb') as stream: stream.write(b'before')
        os.chmod(path,0o640)
        with mock.patch('http_support.os.access',return_value=False):
            http_support.atomic_write(path,b'after')
        self.assertEqual(os.stat(path).st_mode & 0o777,0o640)
        link=os.path.join(self.temp,'link.txt')
        os.symlink(path,link)
        http_support.atomic_write(link,b'linked')
        self.assertTrue(os.path.islink(link))
        with open(path,'rb') as stream: self.assertEqual(stream.read(),b'linked')


class ProxyTests(TempCase):
    def test_invalid_mac_stays_empty_200(self):
        render = mock.Mock()
        for value in ['', 'invalid', MAC + ';id', MAC + ':aa']:
            response = localproxy.handle(self.request('xhibit_proxy.php', 'macAddr=' + http_support.urllib.parse.quote_plus(value)),
                                        {'opsIniPath':'/etc/xhibit/ops.ini'}, render)
            self.assertEqual((response.status, response.body), (200, b''))
        self.assertFalse(render.called)

    def test_xml_and_legacy_rotation_argument_contract(self):
        render = mock.Mock(return_value='<?xml version="1.0"?><COURT/>\n')
        settings = {'opsIniPath':'/etc/xhibit/ops.ini'}
        response = localproxy.handle(self.request('xhibit_proxy.php', 'macAddr=' + MAC + '&currentPageIndex=12abc&data_refresh=1'), settings, render)
        self.assertEqual(response.headers[0], ('Content-Type','application/xml'))
        render.assert_called_once_with(MAC, settings['opsIniPath'], 0, 12, None, timeout=None)
        render.reset_mock()
        localproxy.handle(self.request('xhibit_refresh.php', 'macAddr=' + MAC + '&currentPageIndex=1'), settings, render)
        self.assertFalse(render.called)


class ParserCharacterization(TempCase):
    @classmethod
    def setUpClass(cls):
        try:
            import bs4
            import pymysql
        except ImportError:
            raise unittest.SkipTest('Install existing parser dependencies in the development environment')
        import xhibit
        cls.parser = xhibit
        path = os.path.join(os.path.dirname(__file__), 'fixtures', 'xhibit-before.py.txt')
        with io.open(path, encoding='utf-8') as stream:
            baseline = stream.read().split('macAddress = sys.argv[1]')[0]
        cls.legacy = types.ModuleType('legacy_parser')
        with mock.patch('logging.basicConfig'):
            exec(compile(baseline, path, 'exec'), cls.legacy.__dict__)
        cls.legacy.displayError = False

    def test_all_page_types_and_languages_match_original_bytes(self):
        from bs4 import BeautifulSoup
        for welsh, titles in [(False,TITLES), (True,WELSH_TITLES)]:
            for title in titles:
                soup = BeautifulSoup(html_page(title, welsh), 'html.parser')
                old = self.legacy
                old.error = False
                old.pageIsEnglish = True
                self.parser.error = False
                self.parser.pageIsEnglish = True
                expected_type, expected_page = old.formatPageXML(soup, 0, 'one;two')
                actual_type, actual_page = self.parser.formatPageXML(soup, 0, 'one;two')
                self.assertEqual((actual_type, actual_page), (expected_type, expected_page), title)
                expected_contents = old.formatXhibitXML(soup, expected_type)
                actual_contents = self.parser.formatXhibitXML(soup, actual_type)
                self.assertFalse(old.error, title)
                self.assertFalse(self.parser.error, title)
                expected_cdu = old.formatCDU(dict(ROW))[0]
                actual_cdu = self.parser.formatCDU(dict(ROW))[0]
                self.assertEqual(actual_cdu, expected_cdu)
                self.assertEqual(self.parser.formatXML(actual_cdu, actual_page, actual_contents),
                                 old.formatXML(expected_cdu, expected_page, expected_contents), title)
                golden_name=('welsh-' if welsh else 'english-')+cdu.FULL[expected_type]+'.xml'
                with open(os.path.join(os.path.dirname(__file__),'fixtures','xml',golden_name),'rb') as stream:
                    self.assertEqual((self.parser.formatXML(actual_cdu,actual_page,actual_contents)+'\n').encode('utf-8'),stream.read(),golden_name)

    def test_special_characters_and_empty_fields_retain_xml_bytes(self):
        for notice in [None, '', 'A & B < C', 'Welsh ô', 'quote " and apostrophe \'']:
            row = dict(ROW, notification=notice)
            self.assertEqual(self.parser.formatCDU(row), self.legacy.formatCDU(row))

    def test_rotation_and_data_refresh_cli_behaviour(self):
        for index in [None, 0, 1, -1, 999]:
            for refresh in [None, 1]:
                for url in ['one', 'one;two', '']:
                    self.assertEqual(self.parser.formatUrl(url, ROW['pageUrl'], index, refresh),
                                     self.legacy.formatUrl(url, ROW['pageUrl'], index, refresh))

    def test_power_saving_and_notifications_follow_original(self):
        day=datetime.date.today().strftime('%A')
        for enabled in [True,False]:
            schedule=[dict(priority=1,label='Test',day=[day if enabled else 'NOT_A_DAY'],
                           schedule=[{'from':'00:00','to':'23:59'}])]
            row=dict(ROW,powersaveSchedule=json.dumps(schedule),notification='A notice')
            self.assertEqual(self.parser.formatCDU(row),self.legacy.formatCDU(row))
            expected='ENABLED' if enabled else 'DISABLED'
            self.assertIn('<POWER-SAVING>'+expected+'</POWER-SAVING>',self.parser.formatCDU(row)[0])
        schedule=[dict(priority=1,label='Date',date=[str(datetime.date.today())],schedule=[])]
        # Lock the legacy typo's failure instead of silently repairing it in this migration.
        with self.assertRaises(NameError): self.legacy.iterateSchedules(schedule)
        with self.assertRaises(NameError): self.parser.iterateSchedules(schedule)
        real_datetime = datetime.datetime
        for hour, minute, expected in [(9,59,False),(10,0,True),(10,30,True),(11,0,True),(11,1,False)]:
            class FrozenDateTime(object):
                @classmethod
                def now(cls):
                    return real_datetime(2026,10,23,hour,minute)
            with mock.patch.object(datetime, 'datetime', FrozenDateTime):
                ranges = [{'from':'10:00','to':'11:00'}]
                self.assertEqual(self.parser.iterateTimeRange(ranges), expected)
                self.assertEqual(self.legacy.iterateTimeRange(ranges), expected)

    def test_importable_render_resets_state_and_returns_only_xml(self):
        config = os.path.join(self.temp, 'ops.ini')
        with io.open(config, 'w', encoding='utf-8') as stream:
            stream.write('[DATABASE]\nDBConn=mysql:host=localhost\nDBName=localproxy\nDBusername=test\nDBpasswd=secret\n')
        with mock.patch.object(self.parser, 'parseDB', return_value=dict(ROW)):
            for unused in range(2):
                output = self.parser.render(MAC, config, cdu_only=1)
                self.assertTrue(output.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<COURT>'))
                self.assertTrue(output.endswith('</COURT>\n'))
                self.assertNotIn('<PAGE>', output)
                self.assertNotIn('secret', output)


class CDUTests(TempCase):
    def test_all_stylesheets_match_libxslt_reference(self):
        try:
            from lxml import etree
        except ImportError:
            self.skipTest('Development-only lxml reference unavailable on this interpreter')
        for page, name in cdu.FULL.items():
            for language in ('English', 'Welsh'):
                data = xml_fixture(page).replace(b'English', language.encode('ascii'))
                reference = etree.XSLT(etree.parse(os.path.join(CDU, 'xsl', 'new', name+'.xsl')))
                self.assertEqual(cdu.transform(data, 'new/'+name+'.xsl', {}),
                                 bytes(reference(etree.fromstring(data))), (page, language))
        path = os.path.join(CDU, 'xsl', 'new', 'xml2json.xsl')
        self.assertEqual(cdu.transform(xml_fixture(), 'new/xml2json.xsl', {}),
                         bytes(etree.XSLT(etree.parse(path))(etree.fromstring(xml_fixture()))))

    def test_shell_content_and_monitoring(self):
        settings = self.settings()
        fetcher = mock.Mock(return_value=xml_fixture())
        response = cdu.handle(self.request('index.php'), settings, fetcher)
        self.assertIn(b"nextPage('xhibit_content.php')", response.body)
        self.assertFalse(fetcher.called)
        self.assertFalse(os.path.exists(settings['timestampMonitorFile']))
        response = cdu.handle(self.request('xhibit_content.php', 'currentPageIndex=0'), settings, fetcher)
        self.assertEqual(response.status, 200)
        self.assertIn(b'Test Court', response.body)
        fetcher.assert_called_once_with(settings['fetch']+'?macAddr='+http_support.urllib.parse.quote_plus(MAC)+'&currentPageIndex=0', timeout=3.0)
        self.assertTrue(os.path.isfile(settings['timestampMonitorFile']))
        with open(settings['lastUpdatedLocation'],'rb') as stream:
            self.assertEqual(stream.read(),b'Last Updated: 22 October 2026')
        for route in ('data_refresh.php', 'refresh.php', 'last_updated.php'):
            self.assertEqual(cdu.handle(self.request(route), settings).status, 404)

    def test_ampersands_entities_version_and_ignored_xsl_mode(self):
        data = xml_fixture().replace(b'A &amp; B', b'A & B &amp; C &#38; D')
        transformed = mock.Mock(return_value=b'HTML')
        response = cdu.handle(self.request('xhibit_content.php'), self.settings(),
                              lambda *a, **k: data.replace(b'<XSL>new', b'<XSL>old'), transformed)
        self.assertEqual(response.body, b'HTML')
        args = transformed.call_args[0]
        self.assertIn(b'A &amp; B &amp;amp; C &amp;#38; D', args[0])
        self.assertIn(b'<CLIENT><VERSION>1.0.0</VERSION></CLIENT>', args[0])
        self.assertEqual(args[1], 'new/daily-list.xsl')

    def test_missing_duplicate_fields_and_error_responses(self):
        settings = self.settings()
        for data, status, fragment in [
                (b'', 200, b'badInformationContainer'),
                (b'<broken>', 200, b'badInformationContainer'),
                (b'<COURT><bad></COURT>', 500, b''),
                (xml_fixture('unknown'), 200, b'noInformationToDisplayContainer'),
                (xml_fixture().replace(b'<XSL>new</XSL>', b'<XSL/>'), 200, b'noInformationToDisplayContainer'),
                (xml_fixture().replace(b'<TYPE>Daily List</TYPE>', b'<TYPE>Daily List</TYPE><TYPE>No Info</TYPE>'), 200, b'noInformationToDisplayContainer')]:
            response = cdu.handle(self.request('xhibit_content.php'), settings, lambda *a, **k: data)
            self.assertEqual(response.status, status)
            self.assertIn(fragment, response.body)
        response = cdu.handle(self.request('xhibit_content.php'), settings, mock.Mock(side_effect=IOError('timeout')))
        self.assertEqual(response.status, 200)
        self.assertIn(b'badInformationContainer', response.body)

    def test_external_entities_rejected_before_transform(self):
        transform = mock.Mock()
        data = b'<?xml version="1.0"?><!DOCTYPE COURT [<!ENTITY a SYSTEM "file:///etc/passwd">]><COURT>&a;</COURT>'
        response = cdu.handle(self.request('xhibit_content.php'), self.settings(), lambda *a, **k: data, transform)
        self.assertEqual(response.status, 500)
        self.assertFalse(transform.called)
        with self.assertRaises(cdu.DisplayError):
            cdu.parse_xml(data.decode('utf-8').encode('utf-16'))
        with self.assertRaises(cdu.DisplayError):
            cdu.transform(xml_fixture(), '../../etc/passwd', {})

    def test_mac_discovery_empty_query_and_zero_fallback(self):
        self.assertEqual(cdu.mac_address({}, self.settings()), MAC)
        self.assertEqual(cdu.mac_address({}, {}), '00:00:00:00:00:00')
        runner = mock.Mock(return_value=b'aa:bb:cc: \n dd:ee:ff\t\n')
        self.assertEqual(cdu.mac_address({}, {'macAddressCmd':'trusted pipeline'}, runner), 'aa:bb:cc: dd:ee:ff')
        runner.assert_called_once_with(['/bin/sh','-c','trusted pipeline'], timeout=60.0, check=False)
        self.assertEqual(cdu.mac_address({}, {'macAddressCmd':'printf '+MAC+'; exit 1'}), MAC)
        self.assertEqual(cdu.mac_address({'macAddr':''}, self.settings(), runner), '00:00:00:00:00:00')

    def test_screenshot_success_failure_and_cleanup(self):
        def capture(argv, **kwargs):
            self.assertEqual(argv[:4], ['/usr/bin/sudo','-n','-u','xhibit'])
            self.assertEqual(argv[4], '/usr/local/libexec/xhibit-capture')
            return b'\x89PNG\r\n\x1a\nimage'
        response = cdu.screenshot(self.settings(), capture)
        self.assertEqual(response.headers[0], ('Content-Type','image/png'))
        self.assertEqual(os.listdir(self.temp), [])
        response = cdu.screenshot(self.settings(), lambda *a, **k:b'')
        self.assertEqual((response.status,response.body), (200,b''))


class FakeDatabase(object):
    def __init__(self):
        self.events=[]
        self.notices=[]
    def audit(self,*args): self.events.append(args)
    def index(self): return [dict(SITEid=1,CDUid=1,site='Test Court',title='Screen')]
    def site(self,identifier): return dict(id=identifier,title='Test Court',xsl='new',alert=None,
                                          selectorUrl='http://internal/selector.php',pageUrl='http://internal/page.php?',powersaveSchedule='[]')
    def cdu(self,identifier): return dict(ROW,id=identifier,description='Description',ipAddr='192.168.1.10',xsl='new',selectorUrl='http://internal/selector.php')
    def history(self,*args): return []
    def selector(self,*args): return 'http://internal/selector.php'
    def notice(self,*args): self.notices.append(args)
    def update_site(self,*args): self.updated_site=args
    def update_cdu(self,*args): self.updated_cdu=args


class ManagerTests(TempCase):
    def test_views_existing_fields_and_links(self):
        db = FakeDatabase()
        for route in ['index.php','site.php','cdu.php']:
            response = manager.handle(self.request(route,'id=1',user='operator'),{},db,lambda *a,**k:b'')
            self.assertEqual(response.status,200)
            self.assertIn(b'Test Court',response.body)
            self.assertNotIn(b'Database operation failed',response.body)
            self.assertNotIn(b'csrf',response.body)
        response = manager.handle(self.request('cdu.php','id=1',user='operator'),{},db,lambda *a,**k:b'')
        for field in ['macAddress','refresh','url','notification','UpdateCDU','UpdateNotice','CancelNotice']:
            self.assertIn(field.encode('ascii'),response.body)

    def test_no_user_does_not_open_database(self):
        with mock.patch('manager.Database.from_values') as factory:
            response = manager.handle(self.request('index.php'),{})
            self.assertEqual(response.status,200)
            self.assertNotIn(b'site.php?id=',response.body)
            self.assertFalse(factory.called)

    def test_posts_keep_200_without_redirect_and_audit_identity(self):
        db = FakeDatabase()
        response = manager.handle(self.request('cdu.php',post={'id':'1','UpdateNotice':'Update Notice','notification':'Notice'},user='operator'),{},db,lambda *a,**k:b'')
        self.assertEqual(response.status,200)
        self.assertFalse(any(key=='Location' for key,value in response.headers))
        self.assertEqual(db.notices,[('1','Notice')])
        self.assertEqual(db.events[-1],('operator','UPDATE_NOTIFICATION','(1) | Notice'))
        manager.handle(self.request('cdu.php',post={'id':'1','CancelNotice':'Cancel Notice'},user='operator'),{},db,lambda *a,**k:b'')
        self.assertEqual(db.notices[-1],('1',None))

    def test_site_and_cdu_updates_preserve_form_and_audit_contract(self):
        db=FakeDatabase()
        post={'id':'1','UpdateSite':'Update','title':'Court','xsl':'','alert':'undefined',
              'selectorURL':'http://internal/selector','pageURL':'http://internal/page?','powersaveSchedule':'[]'}
        response=manager.handle(self.request('site.php',post=post,user='operator'),{},db)
        self.assertEqual(response.status,200)
        self.assertEqual(db.updated_site,('1',post))
        self.assertEqual(db.events[-1],('operator','UPDATE_SITE','Court |  |  | http://internal/selector | http://internal/page?'))
        post={'id':'1','UpdateCDU':'Update','macAddress':MAC,'title':'Screen','description':'Description',
              'location':'Reception','url':'one;two','xsl':'new','refresh':'15'}
        response=manager.handle(self.request('cdu.php',post=post,user='operator'),{},db,lambda *a,**k:b'')
        self.assertEqual(response.status,200)
        self.assertEqual(db.updated_cdu,('1',post))
        self.assertEqual(db.events[-1][1],'UPDATE_CDU')

    def test_optional_progress_output_remains_available(self):
        response=manager.handle(self.request('index.php',user='operator'),{'ShowProgress':'true'},FakeDatabase())
        self.assertIn(b'Fetching list of CDUs',response.body)

    def test_screenshot_uses_existing_port_and_failure_response(self):
        fetcher=mock.Mock(return_value=b'PNG')
        response=manager.handle(self.request('cduScreenshot.php','ip=192.168.1.10'),{},fetcher=fetcher)
        self.assertEqual(response.body,b'PNG')
        fetcher.assert_called_once_with('http://192.168.1.10:8080/screenshot.php',timeout=10)
        fetcher.side_effect=IOError('offline')
        response=manager.handle(self.request('cduScreenshot.php','ip=192.168.1.10'),{},fetcher=fetcher)
        self.assertEqual(response.status,200)
        self.assertIn(b'Fetching from:',response.body)


class DatabaseTests(unittest.TestCase):
    def database(self, mapped=True):
        conn = mock.Mock()
        profile = {'site':set('id title welshtitle pageurl powersaveschedule'.split()),
                   'cdu':set('id macaddress cdunumber location refresh notification fksite'.split()),
                   'urlmappings':set(['url','cduid'])}
        return Database(conn, 'localproxy', profile)

    def test_parameter_binding_and_model_court_schema(self):
        db = self.database()
        db.query = mock.Mock(return_value=[ROW])
        self.assertEqual(db.parser_row("' OR 1=1--"), ROW)
        sql, args = db.query.call_args[0]
        self.assertNotIn("' OR 1=1--", sql)
        self.assertEqual(args, ("' OR 1=1--",))
        self.assertIn('CDU.cduNumber AS title', sql)
        self.assertIn('JOIN urlMappings', sql)
        db.profile['cdu'].remove('cdunumber')
        with self.assertRaises(ValueError):
            db.parser_row(MAC)

    def test_database_failure_rolls_back_cdu_update(self):
        db=self.database(True)
        db.execute=mock.Mock(side_effect=RuntimeError('database failure'))
        with self.assertRaises(RuntimeError): db.update_cdu(1,dict(ROW,xsl='new'))
        self.assertTrue(db.connection.rollback.called)
        self.assertFalse(db.connection.commit.called)

    def test_manager_preserves_legacy_cdu_only_url_update(self):
        db=self.database(True)
        db.query=mock.Mock(return_value=[{'url':'one'}])
        db.execute=mock.Mock()
        db.update_cdu(1,dict(ROW,xsl='new'))
        self.assertEqual(db.execute.call_count,1)
        self.assertNotIn('urlMappings',db.execute.call_args[0][0])
        self.assertTrue(db.connection.commit.called)


if __name__ == '__main__':
    unittest.main()
