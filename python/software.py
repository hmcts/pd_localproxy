# -*- coding: utf-8 -*-
"""Model Court's fixed-artifact software delivery contract (not an upload API)."""
import hashlib
from http_support import Response


def handle(request, settings):
    # PHP appends php.ini default_charset to text/* only. Pin the observed
    # header explicitly when the target uses a non-empty default_charset.
    content_type = settings.get('checksumContentType', 'text/plain') if request.route == 'checksum.php' else 'application/octet-stream'
    # No user-supplied filename, directory traversal or alternate package selection.
    path = settings['cduArchive']
    try:
        with open(path, 'rb') as stream:
            data = stream.read()
    except IOError:
        data = None
    if request.route == 'checksum.php' and data is not None:
        data = hashlib.sha1(data).hexdigest().encode('ascii')
    return Response(data if data is not None else b'', content_type=content_type)
