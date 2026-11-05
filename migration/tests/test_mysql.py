# -*- coding: utf-8 -*-
"""Opt-in integration tests on an isolated MariaDB/MySQL test service.

Set XHIBIT_TEST_MYSQL_CONFIG to a private INI for a dedicated test server with
AllowTestDatabases=true and CREATE/DROP DATABASE privileges. Production schemas
are never modified: each test uses a fresh xhibit_test_<uuid> database.
"""
import io
import os
import re
import sys
import unittest
import uuid

ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
sys.path.insert(0,os.path.join(ROOT,'pd_localproxy','python'))
from database import Database
from http_support import read_ini


@unittest.skipUnless(os.environ.get('XHIBIT_TEST_MYSQL_CONFIG'),'Dedicated MySQL/MariaDB test service not configured')
class MySQLIntegration(unittest.TestCase):
    def setUp(self):
        settings=read_ini(os.environ['XHIBIT_TEST_MYSQL_CONFIG'])
        if settings.get('AllowTestDatabases','false').lower()!='true':
            self.fail('Dedicated test config must explicitly enable AllowTestDatabases')
        self.admin=Database.from_values(settings)
        self.name='xhibit_test_'+uuid.uuid4().hex
        self.assertTrue(re.match(r'^xhibit_test_[a-f0-9]{32}$',self.name))
        self.admin.execute('CREATE DATABASE '+self.name+' CHARACTER SET utf8mb4')
        self.addCleanup(self.drop)
        settings['DBName']=self.name
        self.db=Database.from_values(settings)
        with io.open(os.path.join(ROOT,'pd_localproxy','manager','xhibit_proxy_schema.sql'),encoding='utf-8') as stream:
            schema=stream.read()
        schema=re.sub(r'--[^\n]*','',schema)
        for statement in schema.split(';'):
            if statement.strip(): self.db.execute(statement)
        self.db.execute('INSERT INTO SITE (title,welshTitle,xsl,selectorUrl,pageUrl,powersaveSchedule) '
                        'VALUES (%s,%s,%s,%s,%s,%s)',('Court','Llys','new','http://internal/selector','http://internal/page?','[]'))
        self.db.execute('INSERT INTO CDU (macAddress,title,cduNumber,location,url,refresh,fkSITE) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                        ('b8:27:eb:67:75:8f','Screen','TESTDISPL01','Room','old-url',15,1))
        self.db.execute('INSERT INTO urlMappings (cduID,url) VALUES (%s,%s)',(1,'mapped-url'))
        self.db.connection.commit()

    def drop(self):
        if getattr(self,'db',None): self.db.close()
        self.admin.execute('DROP DATABASE '+self.name)
        self.admin.close()

    def check_workflow(self):
        self.assertEqual(self.db.validate_schema(),[])
        self.assertEqual(self.db.index()[0]['title'],'Screen')
        row=self.db.parser_row('B8:27:EB:67:75:8F')
        self.assertEqual(row['title'],'TESTDISPL01')
        self.db.audit('operator','UPDATE_CDU','test')
        self.db.notice(1,'A & B')
        self.assertEqual(self.db.cdu(1)['notification'],'A & B')
        self.db.notice(1,None)
        self.assertIsNone(self.db.cdu(1)['notification'])
        self.db.update_cdu(1,dict(macAddress='b8:27:eb:67:75:8f',title='Changed',description='Desc',
                                  location='Room',url='one;two',xsl='new',refresh='20'))
        self.assertEqual(self.db.cdu(1)['url'],'one;two')
        expected='mapped-url' if self.db.has('urlMappings','url') else 'one;two'
        self.assertEqual(self.db.parser_row('b8:27:eb:67:75:8f')['url'],expected)
        self.assertIsNone(self.db.parser_row("' OR 1=1--"))
        self.assertEqual(self.db.query('SELECT eventType FROM AUDIT')[0]['eventType'],'UPDATE_CDU')

    def test_mapped_profile(self): self.check_workflow()

    def test_missing_required_metadata_is_not_silently_substituted(self):
        self.db.execute('DROP TABLE urlMappings')
        self.db.execute('ALTER TABLE SITE DROP COLUMN welshTitle')
        self.db.execute('ALTER TABLE CDU DROP COLUMN cduNumber')
        self.db.connection.commit()
        self.db.profile = None
        missing = self.db.validate_schema()
        for name in ('urlmappings.url', 'site.welshTitle', 'cdu.cduNumber'):
            self.assertIn(name, missing)
        with self.assertRaises(ValueError):
            self.db.parser_row('b8:27:eb:67:75:8f')

    def test_manager_schema_is_optional(self):
        self.db.execute('DROP TABLE AUDIT')
        self.db.execute('DROP TABLE MAC_TO_IP')
        self.db.connection.commit()
        self.db.profile = None
        self.assertEqual(self.db.validate_schema(), [])
        self.assertIn('audit.username', self.db.validate_schema(with_manager=True))


if __name__=='__main__': unittest.main()
