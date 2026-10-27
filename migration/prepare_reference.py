#!/usr/bin/env python3
"""Prepare verified legacy sources OUTSIDE Git, never in a release installation.

No network calls. Reconstructs complete production files from pinned Git objects
and the collected unified diffs, then verifies their recorded byte hashes.
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile

CDU_SHA = '1920448a5c1e528dcec20b84a01d46049c5f5259f096c23ede732450506c7978'
REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SOFTWARE = {'checksum.php': ('a5633f0d84dd4b0fb48a10964bfbd56511353623139dc5214ed973b057ff231e', 202),
            'download.php': ('f39aa68cac5de2ef280d0a816a06c8bf106ae141e70294331c49eff9cb991cc0', 157)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def patched(original, diff):
    lines = original.decode('utf-8').splitlines(True)
    output, position = [], 0
    for line in diff.splitlines(True)[2:]:
        match = re.match(r'^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@', line)
        if match:
            start = int(match.group(1)) - 1
            output.extend(lines[position:start])
            position = start
        elif line.startswith((' ', '-')):
            if position >= len(lines) or lines[position] != line[1:]:
                raise ValueError('Diff context does not match pinned baseline')
            if line[0] == ' ':
                output.append(line[1:])
            position += 1
        elif line.startswith('+'):
            output.append(line[1:])
        else:
            raise ValueError('Incomplete/unsupported diff')
    output.extend(lines[position:])
    return ''.join(output).encode('utf-8')


def transcript_source(transcript, name):
    """Undo terminal tab expansion only if the recorded production hash matches.

    Blank-line/trailing whitespace was lost by the terminal copy. Search at most
    two whitespace bytes, never alter executable tokens or accept a near match.
    """
    text = transcript.split('/var/www/court-display/software/' + name + '\n', 1)[1].split('[xhibit@', 1)[0]
    lines = []
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip(' '))
        lines.append('\t' * (indent // 8) + ' ' * (indent % 8) + line[indent:])
    raw = ('\n'.join(lines) + '\n').encode('utf-8')
    expected, size = SOFTWARE[name]
    if not 0 <= size - len(raw) <= 2:
        raise ValueError('Transcript is not reconstructable within the whitespace limit')
    candidates = {raw}
    for unused in range(size - len(raw)):
        candidates = {value[:index] + char + value[index:] for value in candidates
                      for index in range(len(value) + 1) if index == len(value) or value[index:index+1] == b'\n'
                      for char in (b' ', b'\t', b'\n')}
    for value in candidates:
        if digest(value) == expected:
            return value
    raise ValueError('Transcript cannot reproduce recorded production hash')


def prepare(archive_path, report_path, destination, software_transcript=None):
    destination = os.path.realpath(destination)
    workspace = os.path.dirname(REPO)
    if destination == workspace or destination.startswith(workspace + os.sep):
        raise ValueError('Legacy reference must remain outside the repositories/workspace')
    os.makedirs(destination, mode=0o700)
    with open(archive_path, 'rb') as stream:
        archive_bytes = stream.read()
    if digest(archive_bytes) != CDU_SHA:
        raise ValueError('Not the verified Model Court v2 archive')
    manifest = {'cdu_archive_sha256': CDU_SHA, 'files': {}}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:') as archive:
        members = archive.getmembers()
        if len(members) != 21:
            raise ValueError('Unexpected distribution member count')
        for entry in members:
            if not entry.isfile() or entry.name.startswith('/') or '..' in entry.name.split('/'):
                raise ValueError('Unsafe reference member')
            data = archive.extractfile(entry).read()
            path = os.path.join(destination, 'cdu', entry.name)
            parent = os.path.dirname(path)
            if not os.path.isdir(parent): os.makedirs(parent, mode=0o700)
            with open(path, 'wb') as stream: stream.write(data)
            os.chmod(path, 0o600)
            manifest['files']['cdu/' + entry.name] = digest(data)
    with io.open(report_path, encoding='utf-8-sig') as stream:
        report = json.load(stream)
    commit = report['baselines']['proxy']['commit']
    manifest['proxy_baseline_commit'] = commit
    for entry in report['files']:
        if entry['repo_path'] not in ('proxy/xhibit.py', 'proxy/xhibit_proxy.php'):
            continue
        original = subprocess.check_output(['git', '-C', REPO, 'show', commit + ':' + entry['repo_path']])
        data = patched(original, entry['redacted_diff'])
        if digest(data) != entry['production_sha256'] or len(data) != entry['size']:
            raise ValueError('Reconstructed source does not match production bytes')
        name = os.path.basename(entry['repo_path'])
        with open(os.path.join(destination, name), 'wb') as stream: stream.write(data)
        os.chmod(os.path.join(destination, name), 0o600)
        manifest['files'][name] = digest(data)
    if software_transcript:
        with io.open(software_transcript, encoding='utf-8') as stream: transcript = stream.read(1024 * 1024)
        os.mkdir(os.path.join(destination, 'software'), mode=0o700)
        for name in sorted(SOFTWARE):
            data = transcript_source(transcript, name)
            with open(os.path.join(destination, 'software', name), 'wb') as stream: stream.write(data)
            os.chmod(os.path.join(destination, 'software', name), 0o600)
            manifest['files']['software/' + name] = digest(data)
    with io.open(os.path.join(destination, 'provenance.json'), 'w', encoding='utf-8') as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--comparison-report', required=True)
    parser.add_argument('--reference-dir', required=True)
    parser.add_argument('--software-transcript', help='Optional previously collected terminal source; hash verified after tab reconstruction')
    args = parser.parse_args()
    print(json.dumps(prepare(args.archive, args.comparison_report, args.reference_dir, args.software_transcript), indent=2, sort_keys=True))
