#!/usr/bin/env python3
"""Regenerate synthetic XML goldens from the hash-verified Model Court parser."""
import hashlib
import io
import os
import sys
import types
from unittest import mock

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from test_compatibility import ROW, TITLES, WELSH_TITLES, html_page
from bs4 import BeautifulSoup
from cdu import FULL


def refresh():
    source = os.path.join(ROOT, 'tests', 'fixtures', 'xhibit-before.py.txt')
    with open(source, 'rb') as stream: raw = stream.read()
    if hashlib.sha256(raw).hexdigest() != '3da9f12fa2df213dd8b4c49579bf6252644dda7a6b0179cdcd1790cbfad30534':
        raise ValueError('Golden source must match the captured production hash')
    parser = types.ModuleType('reference_parser')
    with mock.patch('logging.basicConfig'):
        exec(compile(raw.decode('utf-8').split('macAddress = sys.argv[1]')[0], source, 'exec'), parser.__dict__)
    parser.displayError = False
    for welsh, titles in [(False, TITLES), (True, WELSH_TITLES)]:
        for title in titles:
            parser.error, parser.pageIsEnglish = False, True
            soup = BeautifulSoup(html_page(title, welsh), 'html.parser')
            page_type, page = parser.formatPageXML(soup, 0, 'one;two')
            cdu = parser.formatCDU(dict(ROW))[0]
            contents = parser.formatXhibitXML(soup, page_type)
            data = (parser.formatXML(cdu, page, contents) + '\n').encode('utf-8')
            name = ('welsh-' if welsh else 'english-') + FULL[page_type] + '.xml'
            with open(os.path.join(ROOT, 'tests', 'fixtures', 'xml', name), 'wb') as stream:
                stream.write(data)


if __name__ == '__main__':
    refresh()
