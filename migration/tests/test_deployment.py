# -*- coding: utf-8 -*-
"""Package and real Apache CGI tests, using only disposable directories and loopback."""
import base64
import atexit
import glob
import io
import json
import os
import pwd
import grp
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
DEPLOY = os.path.join(ROOT,'pd_localproxy','migration','deploy.py')


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.mkdtemp(prefix='xhibit-package-test-')
        self.addCleanup(shutil.rmtree,self.temp)

    def test_packages_have_no_php_secrets_or_world_writable_files(self):
        for role in ['localproxy','cdu']:
            output=os.path.join(self.temp,role+'.tar.gz')
            subprocess.check_output([sys.executable,DEPLOY,'package',role,'--python',sys.executable,'--output',output])
            with tarfile.open(output) as archive:
                names=archive.getnames()
                self.assertFalse(any(name.endswith(('.php','.ini','.pyc')) for name in names))
                self.assertTrue('cgi-bin/xhibit.cgi' in names)
                self.assertEqual(archive.getmember('cgi-bin/xhibit.cgi').mode,0o755)
                self.assertFalse(any(entry.mode & 0o022 for entry in archive.getmembers()))
                manifest=json.loads(archive.extractfile('MANIFEST.sha256.json').read().decode('utf-8'))
                self.assertIn('python/http_support.py',manifest)
                self.assertTrue(archive.extractfile('cgi-bin/xhibit.cgi').read().startswith(('#!'+sys.executable+'\n').encode('utf-8')))

    def test_python34_syntax_for_all_runtime_code(self):
        import ast
        for folder in ['pd_localproxy/python','pd_localproxy/proxy','pd_cdu/python','pd_localproxy/migration']:
            for parent,dirs,names in os.walk(os.path.join(ROOT,folder)):
                dirs[:]=[name for name in dirs if name not in ['__pycache__','tests']]
                for name in names:
                    if name.endswith('.py'):
                        with io.open(os.path.join(parent,name),encoding='utf-8') as stream: source=stream.read()
                        # feature_version is available on the development interpreter, not needed on target 3.4.
                        if sys.version_info >= (3,8):
                            ast.parse(source,feature_version=(3,4))
                        else:
                            ast.parse(source)

    def test_screenshot_helper_streams_and_cleans_as_capture_owner(self):
        import contextlib
        import runpy
        import uuid
        from unittest import mock
        helper=os.path.join(ROOT,'pd_localproxy','migration','xhibit-capture')
        basename=uuid.uuid4().hex+'-www-data'
        target='/tmp/'+basename+'.png'
        self.addCleanup(lambda: os.unlink(target) if os.path.exists(target) else None)
        output=io.BytesIO()
        stdout=type('BinaryStdout',(object,),{'buffer':output})()
        def capture(*args,**kwargs):
            with open(target,'wb') as stream: stream.write(b'PNG fixture')
            process=mock.Mock()
            process.communicate.return_value=(b'',b'')
            return process
        with mock.patch('sys.argv',[helper,basename]), mock.patch('sys.stdout',stdout), mock.patch('signal.signal'), mock.patch('subprocess.Popen',side_effect=capture):
            runpy.run_path(helper,run_name='__main__')
        self.assertEqual(output.getvalue(),b'PNG fixture')
        self.assertFalse(os.path.exists(target))
        for invalid in ['../outside','name-with-spaces -f other','a'*32+'-www-data\n']:
            with mock.patch('sys.argv',[helper,invalid]), self.assertRaises(SystemExit) as exc:
                runpy.run_path(helper,run_name='__main__')
            self.assertEqual(exc.exception.code,2)

    def test_preflight_validates_verified_model_court_stylesheets(self):
        if not shutil.which('xsltproc'): self.skipTest('xsltproc unavailable')
        config=os.path.join(self.temp,'cdu.ini')
        with io.open(config,'w',encoding='utf-8') as stream:
            stream.write('[HOST]\nlastUpdatedLocation='+os.path.join(self.temp,'updated')+'\ntimestampMonitorFile='+os.path.join(self.temp,'lastRun')+'\n[SCREENSHOT]\nscreenshotScript='+__file__+'\n')
        os.chmod(config,0o600)
        process=subprocess.Popen([sys.executable,DEPLOY,'preflight','cdu','--install-root',os.path.join(ROOT,'pd_cdu'),'--config',config],stdout=subprocess.PIPE)
        report=json.loads(process.communicate()[0].decode('utf-8'))
        self.assertNotIn('Invalid/missing stylesheet: new/no-info.xsl',report['failures'])
        self.assertTrue(any('config key' in failure for failure in report['failures']))
        self.assertFalse(os.path.exists(os.path.join(self.temp,'updated')))


class ApacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd=shutil.which('httpd') or shutil.which('apache2')
        cls.modules=next((path for path in ['/usr/libexec/apache2','/usr/lib64/httpd/modules','/usr/lib/apache2/modules']
                          if os.path.isfile(os.path.join(path,'mod_cgi.so'))),None)
        if not cls.httpd or cls.modules is None or os.geteuid()==0:
            raise unittest.SkipTest('Local Apache modules unavailable; run generated fragments on pilot hosts')
        cls.temp=tempfile.mkdtemp(prefix='xhibit-apache-test-')
        cls.server=None
        # addClassCleanup was introduced after Python 3.4.
        atexit.register(cls.cleanup)
        install=os.path.join(cls.temp,'app')
        os.mkdir(install)
        # Merge the two independent distributions for isolated route testing.
        # Localproxy python files and the CDU handler/templates coexist in this test installation.
        for role in ['localproxy','cdu']:
            package=os.path.join(cls.temp,role+'.tar.gz')
            subprocess.check_output([sys.executable,DEPLOY,'package',role,'--python',sys.executable,'--output',package] + (['--with-manager'] if role=='localproxy' else []))
            with tarfile.open(package) as archive:
                for entry in archive.getmembers():
                    if role=='cdu' and entry.name=='cgi-bin/xhibit.cgi': continue
                    destination=os.path.join(install,entry.name)
                    parent=os.path.dirname(destination)
                    if not os.path.isdir(parent): os.makedirs(parent)
                    with open(destination,'wb') as stream: stream.write(archive.extractfile(entry).read())
                    os.chmod(destination,entry.mode)
        # CDU requires its own CGI entry point, sharing only helpers.
        cdu_entry=os.path.join(install,'cgi-bin','cdu.cgi')
        source=os.path.join(ROOT,'pd_cdu','cgi-bin','xhibit.cgi')
        with open(source,'rb') as stream: data=stream.read().split(b'\n',1)[1]
        with open(cdu_entry,'wb') as stream: stream.write(('#!'+sys.executable+'\n').encode('utf-8')+data)
        os.chmod(cdu_entry,0o755)
        ops=os.path.join(cls.temp,'ops.ini')
        with io.open(ops,'w',encoding='utf-8') as stream: stream.write('[DATABASE]\nDBConn=mysql:host=localhost\nDBName=test\nDBusername=test\nDBpasswd=test\n')
        cduconfig=os.path.join(cls.temp,'cdu.ini')
        state=os.path.join(cls.temp,'updated.txt')
        with open(state,'wb') as stream: stream.write(b'Last Updated: pilot')
        with io.open(cduconfig,'w',encoding='utf-8') as stream:
            stream.write('[HOST]\nlastUpdatedLocation='+state+'\ndefaultMacAddress=\ntimestampMonitorFile='+os.path.join(cls.temp,'lastRun.txt')+'\n[PROXY]\ntimeout=0.1\nfetch=http://127.0.0.1:1/proxy.php\nrefresh=http://127.0.0.1:1/refresh.php\n')
        password=os.path.join(cls.temp,'password')
        subprocess.check_output([shutil.which('htpasswd'),'-bc',password,'operator','pilot-test-password'],stderr=subprocess.STDOUT)
        auth=os.path.join(cls.temp,'auth.conf')
        with io.open(auth,'w',encoding='utf-8') as stream:
            stream.write('AuthType Basic\nAuthName "Pilot"\nAuthUserFile "'+password+'"\nRequire valid-user\n')
        fragments=os.path.join(cls.temp,'routes')
        subprocess.check_output([sys.executable,DEPLOY,'apache','localproxy','--install-root',install,'--config',ops,'--with-manager','--auth-config',auth,'--output',fragments])
        # Simulate the final per-route cutover, including the deny rule.
        for path in glob.glob(os.path.join(fragments,'*.disabled')): os.rename(path,path[:-len('.disabled')])
        cdu_fragments=os.path.join(cls.temp,'cdu-routes')
        subprocess.check_output([sys.executable,DEPLOY,'apache','cdu','--install-root',install,'--config',cduconfig,'--output',cdu_fragments])
        for path in glob.glob(os.path.join(cdu_fragments,'*')):
            with io.open(path,encoding='utf-8') as stream: data=stream.read()
            with io.open(path,'w',encoding='utf-8') as stream:
                stream.write(data.replace('/cgi-bin/xhibit.cgi','/cgi-bin/cdu.cgi'))
            if path.endswith('.disabled'): os.rename(path,path[:-len('.disabled')])
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            cls.port=sock.getsockname()[1]
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            cls.cdu_port=sock.getsockname()[1]
        config=os.path.join(cls.temp,'httpd.conf')
        modules=['mpm_prefork','authz_core','authz_host','authz_user','authn_core','authn_file','auth_basic','alias','env','cgi','mime','dir','unixd']
        conf='ServerRoot "'+cls.temp+'"\n'
        conf+='DefaultRuntimeDir "'+cls.temp+'"\nMutex file:'+cls.temp+' default\n'
        conf+='\n'.join('LoadModule {0}_module "{1}/mod_{0}.so"'.format(name,cls.modules)
                        for name in modules if os.path.isfile(os.path.join(cls.modules,'mod_'+name+'.so')))+'\n'
        conf+='Listen 127.0.0.1:{0}\nListen 127.0.0.1:{2}\nServerName 127.0.0.1\nPidFile "{1}/httpd.pid"\nErrorLog "{1}/error.log"\n'.format(cls.port,cls.temp,cls.cdu_port)
        conf+='User '+pwd.getpwuid(os.getuid()).pw_name+'\nGroup '+grp.getgrgid(os.getgid()).gr_name+'\n'
        conf+='DocumentRoot "'+install+'"\n<Directory "'+install+'">\nRequire all denied\n</Directory>\n'
        mime=next(path for path in ['/private/etc/apache2/mime.types','/etc/mime.types','/etc/httpd/conf/mime.types'] if os.path.isfile(path))
        conf+='TypesConfig '+mime+'\n'
        conf+='<VirtualHost 127.0.0.1:{0}>\nInclude "{1}/*.conf"\n</VirtualHost>\n'.format(cls.port,fragments)
        conf+='<VirtualHost 127.0.0.1:{0}>\nInclude "{1}/*.conf"\n</VirtualHost>\n'.format(cls.cdu_port,cdu_fragments)
        with io.open(config,'w',encoding='utf-8') as stream: stream.write(conf)
        validation=subprocess.Popen([cls.httpd,'-t','-f',config],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        result=validation.communicate()[0]
        if validation.returncode: raise AssertionError(result.decode('utf-8','replace'))
        cls.server=subprocess.Popen([cls.httpd,'-X','-f',config],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        deadline=time.time()+5
        while time.time()<deadline:
            if cls.server.poll() is not None:
                raise AssertionError(cls.server.communicate()[1].decode('utf-8','replace'))
            try:
                urllib.request.urlopen('http://127.0.0.1:{0}/proxy/xhibit_proxy.php'.format(cls.port),timeout=1)
                break
            except urllib.error.HTTPError:
                break
            except IOError:
                time.sleep(0.05)
        else: raise AssertionError('Apache failed to start')

    @classmethod
    def cleanup(cls):
        if cls.server is not None:
            if cls.server.poll() is None:
                cls.server.terminate()
            try: cls.server.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                cls.server.kill()
                cls.server.communicate()
            finally: cls.server = None
        if getattr(cls,'temp',None) and os.path.isdir(cls.temp): shutil.rmtree(cls.temp)

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()

    def fetch(self,path,authenticated=False,port=None):
        request=urllib.request.Request('http://127.0.0.1:{0}{1}'.format(port or self.port,path))
        if authenticated:
            request.add_header('Authorization','Basic '+base64.b64encode(b'operator:pilot-test-password').decode('ascii'))
        try:
            with urllib.request.urlopen(request,timeout=3) as response:
                return response.getcode(),response.read()
        except urllib.error.HTTPError as exc:
            return exc.code,exc.read()

    def test_verified_proxy_alias_executes_python_and_refresh_is_absent(self):
        self.assertEqual(self.fetch('/proxy/xhibit_proxy.php'), (200,b''))
        self.assertIn(self.fetch('/proxy/xhibit_refresh.php')[0], [403,404])

    def test_unknown_php_and_source_files_are_denied(self):
        for path in ['/arbitrary.php','/python/manager.py','/proxy/xhibit.py']:
            self.assertIn(self.fetch(path)[0],[403,404],path)

    def test_manager_authentication_and_directory_alias(self):
        self.assertEqual(self.fetch('/manager/index.php')[0],401)
        self.assertEqual(self.fetch('/manager/')[0],401)
        for endpoint in ['index.php','site.php?id=1','cdu.php?id=1','']:
            self.assertEqual(self.fetch('/manager/'+endpoint,True)[0],200,endpoint)

    def test_cdu_model_court_routes(self):
        self.assertEqual(self.fetch('/index.php',port=self.cdu_port)[0],200)
        self.assertEqual(self.fetch('/',port=self.cdu_port)[0],200)
        status, body = self.fetch('/xhibit_content.php',port=self.cdu_port)
        self.assertEqual(status,200)
        self.assertIn(b'No Information To Display',body)
        for route in ('last_updated.php','refresh.php','data_refresh.php'):
            self.assertIn(self.fetch('/'+route,port=self.cdu_port)[0],[403,404])

    def test_cdu_static_scripts_are_public_without_exposing_python(self):
        for path in ['/display_documentNEW.js','/jquery-3.1.1.min.js','/onscreen-clock.js','/localError.html']:
            status, body = self.fetch(path,port=self.cdu_port)
            self.assertEqual(status,200,path)
            self.assertTrue(body,path)
        self.assertIn(self.fetch('/python/cdu.py',port=self.cdu_port)[0],[403,404])


if __name__=='__main__': unittest.main()
