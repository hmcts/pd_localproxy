# -*- coding: utf-8 -*-
"""Port of the legacy manager controller/views; URLs and POST flow are retained.

Security-only differences from the PHP manager: every substituted value is
HTML-escaped, state-changing POSTs need a per-user CSRF token (and a same-origin
Origin/Referer when the browser sends one), and cduScreenshot.php accepts only an
IPv4 address or host name and relays only PNG bodies.
"""
import hashlib
import hmac
import html
import io
import os
import re
import string
import urllib.parse
from database import Database
from http_support import Response, fetch, log

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
CSRF_FIELD = 'csrfToken'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
SCREENSHOT_LIMIT = 16 * 1024 * 1024
IPV4 = re.compile(r'^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}'
                  r'(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\Z')
HOST_LABEL = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z')


def text(value):
    return '' if value is None else str(value)


def escape(value):
    return html.escape(text(value), quote=True)


def url_text(value):
    # Percent-encode only characters that are never valid in a URL. Reserved
    # characters and existing %-escapes are kept, so valid links are unchanged.
    return urllib.parse.quote(text(value), safe="!#$%&'()*+,/:;=?@[]~")


def fragment(name, values=None):
    with io.open(os.path.join(TEMPLATES, name + '.html'), encoding='utf-8') as stream:
        source = stream.read()
    # Patch-created template files have one terminating newline; PHP heredocs do not emit it.
    source = source[:-1] if source.endswith('\n') else source
    return string.Template(source).substitute(dict((key, escape(value))
                                                   for key, value in (values or {}).items()))


def screenshot_host(value):
    """Return value when it is a dotted IPv4 address or an RFC 1123 host name."""
    if IPV4.match(value):
        return value
    labels = value.split('.')
    # An all-numeric final label is not a host name; it may be an alternative IPv4 form.
    if (len(value) > 253 or not all(HOST_LABEL.match(label) for label in labels)
            or labels[-1].isdigit()):
        return None
    return value


def csrf_token(settings, user):
    # Keyed by the private manager configuration: an explicit managerCsrfSecret,
    # otherwise the database credentials Apache already reads from the root-owned INI.
    secret = settings.get('managerCsrfSecret') or '\0'.join(
        text(settings.get(key)) for key in ('DBConn', 'DBName', 'DBusername', 'DBpasswd'))
    key = hashlib.sha256(('xhibit-manager-csrf\0' + secret).encode('utf-8')).digest()
    return hmac.new(key, text(user).encode('utf-8'), hashlib.sha256).hexdigest()


def same_origin(environ):
    host = environ.get('HTTP_HOST', '').strip().lower()
    for header in ('HTTP_ORIGIN', 'HTTP_REFERER'):
        value = environ.get(header)
        if value is None:
            continue
        try:
            source = urllib.parse.urlsplit(value.strip())
        except ValueError:
            return False
        if not host or source.scheme not in ('http', 'https') or source.netloc.lower() != host:
            return False
    return True


def csrf_valid(request, settings):
    supplied = request.post.get(CSRF_FIELD, '')
    expected = csrf_token(settings, request.user)
    return (same_origin(request.environ) and
            hmac.compare_digest(supplied.encode('utf-8'), expected.encode('ascii')))


def xsl_options(value, allow_unset=False):
    result = ''
    if allow_unset:
        result += '<option{0} value="">Not Set</option>'.format(' selected' if value is None else '')
    for key, label in (('old', 'Current'), ('new', 'New')):
        result += '<option{0} value="{1}">{2}</option>'.format(' selected' if value == key else '', key, label)
    return result


def available_pages(content):
    labels, values = [], []
    for line in content.decode('utf-8', 'replace').split('\n'):
        if not re.search(r'class="display-location|onClick=\x27selectDisplay', line):
            continue
        if 'class="display-location"' in line:
            begin = line.find('>') + 1
            labels.append(line[begin:line.find('<', begin)])
        if 'selectDisplay' in line:
            begin = line.find('selectDisplay(')
            end = line.find(')', begin + 15)
            values.append(line[begin + 15:end - 1])
    return list(zip(labels, values))


def index_view(rows, user):
    values = {'authenticatedUser': user}
    out = fragment('index-START')
    if not user:
        return out
    out += fragment('index-USER', values) + fragment('index-CDU')
    out += '\t\t<section id="CDUlist">\n\n\t\t\t<table class="output">\n'
    out += '\t\t\t</table><br/>\n\t\t\t<center><table class="results">\n'
    out += '\t\t\t\t<th>Site</th><th>CDUs</th>\n'
    seen = set()
    for site in rows:
        if site['SITEid'] in seen:
            continue
        seen.add(site['SITEid'])
        out += '\t\t\t\t<tr>\n'
        out += '\t\t\t\t\t<td class="results"><a href="site.php?id={0}">{1}</a></td>\n'.format(
            escape(urllib.parse.quote(text(site['SITEid']), safe='')), escape(site['site']))
        out += '\t\t\t\t\t<td class="results">\n'
        for cdu in rows:
            if cdu['SITEid'] == site['SITEid']:
                out += '\t\t\t\t\t\t<a href="cdu.php?id={0}">{1}</a><br/>\n'.format(
                    escape(urllib.parse.quote(text(cdu['CDUid']), safe='')), escape(cdu['title']))
        out += '\t\t\t\t\t</td>\n</tr>\n'
    out += '\t\t\t</table></center>\n\t\t</section>\n'
    return out + fragment('index-END')


def site_view(row, identifier, user, token=''):
    row = row or {}
    values = dict(row, SITEindex=identifier, authenticatedUser=user, csrfToken=token,
                  alert='undefined' if row.get('alert') is None else row['alert'])
    values['selectorURL'] = row.get('selectorUrl', '')
    values['pageURL'] = row.get('pageUrl', '')
    values.setdefault('title', '')
    out = fragment('site-START', values)
    if not user:
        return out
    out += fragment('site-USER', values) + fragment('site-CDU')
    out += '\t\t<section id="info">\n\n\t\t\t<table class="output">\n\t\t\t</table>\n</section><br/>\n'
    if row:
        out += fragment('site-SITE', values) + xsl_options(row.get('xsl')) + fragment('site-SITE-2', values)
    return out + fragment('site-END')


def cdu_view(row, identifier, user, settings, pages, token=''):
    row = row or {}
    values = dict(row, CDUindex=identifier, CDUsite=row.get('site', ''), csrfToken=token,
                  authenticatedUser=user, CDUip=urllib.parse.quote_plus(text(row.get('ipAddr'))),
                  notice='undefined' if row.get('notification') is None else row['notification'])
    out = fragment('cdu-START', values)
    if not user:
        return out
    out += fragment('cdu-USER', values) + fragment('cdu-CDU')
    out += '\t\t<section id="info">\n\n\t\t\t<table class="output">\n\t\t\t</table>\n</section><br/>\n'
    if row:
        values['xhibitUrl'] = settings.get('url', '') + url_text(row['url'])
        values['proxyHttpUrl'] = settings.get('proxy', '') + '?macAddr=' + urllib.parse.quote_plus(row['macAddress'])
        values['cduHttpUrl'] = settings.get('cdu', '') + '?macAddr=' + urllib.parse.quote_plus(row['macAddress'])
        out += fragment('cdu-CONTROL_REMOTE_CONTROL_PANEL', values)
        out += fragment('cdu-NOTIFICATION', values) + fragment('cdu-CDU1', values)
        out += xsl_options(row.get('xsl'), True) + fragment('cdu-CDU2', values) + '\n'
        for label, url in pages:
            selected = ' selected="selected"' if url == row['url'] else ' '
            out += '                    <option value="{0}"{1}>{2}</option>\n'.format(escape(url), selected, escape(label))
        out += fragment('cdu-CDU3')
    return out + fragment('cdu-END')


def handle(request, settings, database=None, fetcher=fetch):
    route = request.route or 'index.php'
    content_type = settings.get('defaultContentType', 'text/html; charset=UTF-8')
    if route == 'cduScreenshot.php':
        host = request.query.get('ip', '')
        target = 'http://{0}:8080/screenshot.php'.format(host)
        try:
            if screenshot_host(host) is None:
                raise ValueError('invalid screenshot host')
            data = fetcher(target, timeout=10, limit=SCREENSHOT_LIMIT)
            if not data.startswith(PNG_SIGNATURE):
                raise ValueError('screenshot response is not a PNG')
            return Response(data, content_type='image/png')
        except Exception:
            return Response('<html>\n\t<body>\n\t\t<p>Fetching from: {0}</p>\n\t</body>\n</html>\n'.format(escape(target)), content_type=content_type)
    kind = {'index.php': 'index', 'site.php': 'site', 'cdu.php': 'cdu'}.get(route)
    if not kind:
        return Response(status=404)
    identifier = request.query.get('id', request.post.get('id', ''))
    if not request.user:
        # Like the PHP views, an unauthenticated page shows no requested index.
        view = index_view([], None) if kind == 'index' else (site_view(None, '', None)
                if kind == 'site' else cdu_view(None, '', None, settings, []))
        return Response(fragment(kind + '-head') + view + '\n\t\n</body>\n</table>', content_type=content_type)
    if request.environ.get('REQUEST_METHOD') == 'POST' and not csrf_valid(request, settings):
        log('MANAGER_CSRF_REJECTED')
        return Response(fragment(kind + '-head') + '<p class="error">Error: Request could not be verified. '
                        'Reload the page and try again.</p>\n</body>\n</table>', status=403, content_type=content_type)
    token = csrf_token(settings, request.user)
    owned = database is None
    try:
        database = database or Database.from_values(settings)
        post = request.post
        progress = []
        if kind == 'index':
            progress.append('Fetching list of CDUs')
            database.audit(request.user, 'FETCHING_CDUS')
            view = index_view(database.index(), request.user)
        elif kind == 'site':
            progress.append('Fetching SITE')
            if 'id' not in request.query:
                progress.append('Get SITE [{0}] index from POST'.format(identifier))
            database.audit(request.user, 'FETCH_SITE')
            if 'UpdateSite' in post:
                progress.append('Updating SITE with index [{0}]'.format(identifier))
                alert = post.get('alert')
                alert = None if alert in ('', 'undefined') else alert
                audit = ' | '.join(text(value) for value in
                    (post.get('title'), post.get('xsl') or None, alert,
                     post.get('selectorURL'), post.get('pageURL')))
                database.audit(request.user, 'UPDATE_SITE', audit)
                database.update_site(identifier, post)
                progress.append('....success.')
            progress.append('... with index [{0}]'.format(identifier))
            view = site_view(database.site(identifier), identifier, request.user, token)
        else:
            progress.append('Fetching CDU')
            if 'id' not in request.query:
                progress.append('Get CDU [{0}] index from POST'.format(identifier))
            database.audit(request.user, 'FETCH_CDU', '({0})'.format(identifier))
            if 'UpdateCDU' in post:
                progress.append('Updating CDU with index [{0}]'.format(identifier))
                audit = '({0}) | '.format(identifier) + ' | '.join(text(post.get(key)) for key in
                    ('title','description','location','macAddress','refresh','xsl','url'))
                database.audit(request.user, 'UPDATE_CDU', audit)
                database.update_cdu(identifier, post)
                progress.append('....success.')
            if 'UpdateNotice' in post:
                progress.append('Updating CDU notification with index [{0}]'.format(identifier))
                database.audit(request.user, 'UPDATE_NOTIFICATION', '({0}) | {1}'.format(identifier, post.get('notification', '')))
                database.notice(identifier, post.get('notification', ''))
                progress.append('....success.')
            if 'CancelNotice' in post:
                progress.append('Cancelling CDU notification with index [{0}]'.format(identifier))
                database.audit(request.user, 'RESET_NOTIFICATION', '({0})'.format(identifier))
                database.notice(identifier, None)
                progress.append('....success.')
            progress.append('... with index [{0}]'.format(identifier))
            row = database.cdu(identifier)
            # The old controller also reads IP history, even though the view does not display it.
            database.history(identifier, settings.get('MaxRecordCount', 10))
            pages = []
            selector = database.selector(identifier)
            if row and selector:
                try:
                    pages = available_pages(fetcher(selector, timeout=60))
                except Exception:
                    pass  # Legacy selector failures leave the helper dropdown empty.
            view = cdu_view(row, identifier, request.user, settings, pages, token)
        if settings.get('ShowProgress', 'false').lower() == 'true':
            progress.extend(getattr(database, 'progress', []))
            rows = ''.join('\t\t\t<tr><td class="output">{0}</td></tr>\n'.format(escape(line)) for line in progress)
            marker = '<table class="output">\n'
            view = view.replace(marker, marker + rows, 1)
        return Response(fragment(kind + '-head') + view + '\n\t\n</body>\n</table>', content_type=content_type)
    except Exception as exc:
        log('MANAGER_FAILURE ' + type(exc).__name__)
        return Response(fragment(kind + '-head') + '<p class="error">Error: Database operation failed.</p>\n</body>\n</table>', content_type=content_type)
    finally:
        if owned and database is not None:
            database.close()
