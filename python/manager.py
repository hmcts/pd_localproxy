# -*- coding: utf-8 -*-
"""Port of the legacy manager controller/views; URLs and POST flow are retained."""
import io
import os
import re
import string
import urllib.parse
from database import Database
from http_support import Response, fetch, log

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')


def text(value):
    return '' if value is None else str(value)


def fragment(name, values=None):
    with io.open(os.path.join(TEMPLATES, name + '.html'), encoding='utf-8') as stream:
        source = stream.read()
    # Patch-created template files have one terminating newline; PHP heredocs do not emit it.
    source = source[:-1] if source.endswith('\n') else source
    return string.Template(source).substitute(dict((key, text(value))
                                                   for key, value in (values or {}).items()))


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
        out += '\t\t\t\t\t<td class="results"><a href="site.php?id={0}">{1}</a></td>\n'.format(site['SITEid'], site['site'])
        out += '\t\t\t\t\t<td class="results">\n'
        for cdu in rows:
            if cdu['SITEid'] == site['SITEid']:
                out += '\t\t\t\t\t\t<a href="cdu.php?id={0}">{1}</a><br/>\n'.format(cdu['CDUid'], cdu['title'])
        out += '\t\t\t\t\t</td>\n</tr>\n'
    out += '\t\t\t</table></center>\n\t\t</section>\n'
    return out + fragment('index-END')


def site_view(row, identifier, user):
    row = row or {}
    values = dict(row, SITEindex=identifier, authenticatedUser=user,
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


def cdu_view(row, identifier, user, settings, pages):
    row = row or {}
    values = dict(row, CDUindex=identifier, CDUsite=row.get('site', ''),
                  authenticatedUser=user, CDUip=urllib.parse.quote_plus(text(row.get('ipAddr'))),
                  notice='undefined' if row.get('notification') is None else row['notification'])
    out = fragment('cdu-START', values)
    if not user:
        return out
    out += fragment('cdu-USER', values) + fragment('cdu-CDU')
    out += '\t\t<section id="info">\n\n\t\t\t<table class="output">\n\t\t\t</table>\n</section><br/>\n'
    if row:
        values['xhibitUrl'] = settings.get('url', '') + row['url']
        values['proxyHttpUrl'] = settings.get('proxy', '') + '?macAddr=' + urllib.parse.quote_plus(row['macAddress'])
        values['cduHttpUrl'] = settings.get('cdu', '') + '?macAddr=' + urllib.parse.quote_plus(row['macAddress'])
        out += fragment('cdu-CONTROL_REMOTE_CONTROL_PANEL', values)
        out += fragment('cdu-NOTIFICATION', values) + fragment('cdu-CDU1', values)
        out += xsl_options(row.get('xsl'), True) + fragment('cdu-CDU2', values) + '\n'
        for label, url in pages:
            selected = ' selected="selected"' if url == row['url'] else ' '
            out += '                    <option value="{0}"{1}>{2}</option>\n'.format(url, selected, label)
        out += fragment('cdu-CDU3')
    return out + fragment('cdu-END')


def handle(request, settings, database=None, fetcher=fetch):
    route = request.route or 'index.php'
    content_type = settings.get('defaultContentType', 'text/html; charset=UTF-8')
    if route == 'cduScreenshot.php':
        target = 'http://{0}:8080/screenshot.php'.format(request.query.get('ip', ''))
        try:
            return Response(fetcher(target, timeout=10), content_type='image/png')
        except Exception:
            return Response('<html>\n\t<body>\n\t\t<p>Fetching from: {0}</p>\n\t</body>\n</html>\n'.format(target), content_type=content_type)
    kind = {'index.php': 'index', 'site.php': 'site', 'cdu.php': 'cdu'}.get(route)
    if not kind:
        return Response(status=404)
    identifier = request.query.get('id', request.post.get('id', ''))
    if not request.user:
        view = index_view([], None) if kind == 'index' else (site_view(None, identifier, None)
                if kind == 'site' else cdu_view(None, identifier, None, settings, []))
        return Response(fragment(kind + '-head') + view + '\n\t\n</body>\n</table>', content_type=content_type)
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
            view = site_view(database.site(identifier), identifier, request.user)
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
            view = cdu_view(row, identifier, request.user, settings, pages)
        if settings.get('ShowProgress', 'false').lower() == 'true':
            progress.extend(getattr(database, 'progress', []))
            rows = ''.join('\t\t\t<tr><td class="output">{0}</td></tr>\n'.format(line) for line in progress)
            marker = '<table class="output">\n'
            view = view.replace(marker, marker + rows, 1)
        return Response(fragment(kind + '-head') + view + '\n\t\n</body>\n</table>', content_type=content_type)
    except Exception as exc:
        log('MANAGER_FAILURE ' + type(exc).__name__)
        return Response(fragment(kind + '-head') + '<p class="error">Error: Database operation failed.</p>\n</body>\n</table>', content_type=content_type)
    finally:
        if owned and database is not None:
            database.close()
