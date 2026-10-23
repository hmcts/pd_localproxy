# -*- coding: utf-8 -*-
"""Small CGI/INI helpers. Standard library only; Python 3.4+."""
import configparser
import io
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

DEFAULT_CONTENT_TYPE = "text/html; charset=UTF-8"


def read_ini(path):
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    with io.open(path, encoding="utf-8-sig") as stream:
        source = stream.read()
    # Support deployed flat INIs as well as the sectioned examples.
    parser.read_string('[XHIBIT_DEFAULT]\n' + source)
    values = {}
    for section in parser.sections():
        for key, value in parser.items(section):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            values[key] = value
    return values


def php_int(value):
    match = re.match(r"^\s*([+-]?\d+)", str(value))
    return int(match.group(1)) if match else 0


def parameters(encoded):
    # PHP keeps the last scalar value for duplicate parameter names. PHP separates
    # fields only on "&"; Python 3.4 parse_qsl also splits on ";", so split here.
    values = {}
    for field in encoded.split("&"):
        if field:
            name, unused, value = field.partition("=")
            values[urllib.parse.unquote_plus(name)] = urllib.parse.unquote_plus(value)
    return values


class Request(object):
    def __init__(self, environ=None, body=b""):
        self.environ = dict(environ or {})
        self.query = parameters(self.environ.get("QUERY_STRING", ""))
        self.post = {}
        if self.environ.get("REQUEST_METHOD", "GET") == "POST":
            content_type = self.environ.get("CONTENT_TYPE", "").split(";")[0]
            if content_type == "application/x-www-form-urlencoded":
                self.post = parameters(body.decode("utf-8", "replace"))
        self.route = self.environ.get("SCRIPT_NAME", "").rsplit("/", 1)[-1]
        self.user = self.environ.get("REMOTE_USER") or self.environ.get("PHP_AUTH_USER")

    @classmethod
    def from_cgi(cls):
        count = max(0, int(os.environ.get("CONTENT_LENGTH") or "0"))
        return cls(os.environ, sys.stdin.buffer.read(count))


class Response(object):
    def __init__(self, body=b"", status=200, content_type=DEFAULT_CONTENT_TYPE, headers=None):
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.status = status
        self.headers = [("Content-Type", content_type)] + list(headers or [])

    def emit(self, stream=None):
        stream = stream or sys.stdout.buffer
        reasons = {200: "OK", 204: "No Content", 400: "Bad Request", 403: "Forbidden",
                   404: "Not Found", 500: "Internal Server Error", 503: "Service Unavailable"}
        lines = []
        if self.status != 200:
            lines.append("Status: {0} {1}".format(self.status, reasons.get(self.status, "Error")))
        lines.extend("{0}: {1}".format(*item) for item in self.headers)
        stream.write(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
        stream.write(self.body if self.status != 204 else b"")


def fetch(url, timeout=60, limit=0):
    # Match PHP's stream user-agent: no Python-urllib identifier.
    request = urllib.request.Request(url)
    # PHP streams do not inherit proxy variables; CGI HTTP_PROXY must not alter routing.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    opener.addheaders = []
    with opener.open(request, timeout=timeout) as response:
        data = response.read(limit + 1) if limit else response.read()
        if limit and len(data) > limit:
            raise ValueError("upstream response limit")
        return data


def command(argv, data=None, timeout=60, check=True):
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, close_fds=True)
    try:
        output, errors = process.communicate(data, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
        raise
    if check and process.returncode:
        raise RuntimeError("command failed ({0})".format(process.returncode))
    return output


def atomic_write(path, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    existing = os.stat(path) if os.path.exists(path) else None
    # Existing /var/log files can be group-writable without granting Apache write
    # access to /var/log itself. Retain that permission and ownership contract.
    if existing is not None and (existing.st_uid != os.geteuid() or existing.st_nlink > 1
                                 or os.path.islink(path) or not os.access(directory, os.W_OK)):
        with open(path, "wb") as stream:
            stream.write(data)
        return
    fd, temporary = tempfile.mkstemp(prefix=".xhibit-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        if existing is not None:
            os.chmod(temporary, existing.st_mode & 0o777)
            try:
                os.chown(temporary, existing.st_uid, existing.st_gid)
            except OSError:
                with open(path, "wb") as stream:
                    stream.write(data)
                return
        else:
            # Match ordinary file creation under the CGI process umask.
            mask = os.umask(0)
            os.umask(mask)
            os.chmod(temporary, 0o666 & ~mask)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def log(message, ident="xhibit.cgi", severity=None):
    try:
        import syslog
        syslog.openlog(ident, syslog.LOG_PID, syslog.LOG_LOCAL5)
        syslog.syslog(syslog.LOG_ERR if severity is None else severity, message)
    except (ImportError, OSError):
        pass
