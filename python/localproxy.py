# -*- coding: utf-8 -*-
"""Legacy URLs implemented by Python CGI, without a PHP runtime."""
import os
import re
import sys
from http_support import Request, Response, log, php_int, read_ini

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'proxy'))
MAC = re.compile(r'^[A-Fa-f0-9]{2}(?::[A-Fa-f0-9]{2}){5}$')


def handle(request, settings=None, renderer=None):
    settings = settings or read_ini(os.environ.get('XHIBIT_CONFIG', '/etc/xhibit/ops.ini'))
    content_type = settings.get('defaultContentType', 'text/html; charset=UTF-8')
    if request.route in ('checksum.php', 'download.php'):
        from software import handle as software_handle
        return software_handle(request, settings)
    if request.route in ('index.php', 'site.php', 'cdu.php', 'cduScreenshot.php', '') and os.environ.get('XHIBIT_WITH_MANAGER') == '1':
        from manager import handle as manager_handle
        return manager_handle(request, settings)
    if request.route != 'xhibit_proxy.php':
        return Response(status=404, content_type=content_type)
    mac = request.query.get('macAddr')
    if not mac or not MAC.match(mac):
        # Legacy PHP exits without changing its default 200/html response.
        return Response(content_type=content_type)
    if renderer is None:
        import xhibit
        renderer = xhibit.render
    current = request.query.get('currentPageIndex')
    current = php_int(current) if current is not None else None
    only = 0
    # PHP is_int($_GET['data_refresh']) was always false for HTTP strings.
    # Preserve that observable rotation behaviour until a separate approved fix.
    timeout = settings.get('parserTimeout')
    xml = renderer(mac, settings['opsIniPath'], only, current, None,
                   timeout=float(timeout) if timeout else None)
    return Response(xml, content_type='application/xml')


def main():
    try:
        path = os.environ.get('XHIBIT_CONFIG', '/etc/xhibit/ops.ini')
        values = read_ini(path)
        values['opsIniPath'] = path
        handle(Request.from_cgi(), values).emit()
    except Exception as exc:
        log('LOCALPROXY_FAILURE ' + type(exc).__name__)
        Response(status=500).emit()


if __name__ == '__main__':
    main()
