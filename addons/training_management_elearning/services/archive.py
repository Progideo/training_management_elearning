"""Bounded archive validation. Never extracts untrusted paths to a filesystem."""
import hashlib
import io
import json
import re
import stat
import zipfile
import zlib
from lxml import etree

MAX_ARCHIVE = 20 * 1024 * 1024
MAX_TOTAL = 40 * 1024 * 1024
MAX_FILE = 10 * 1024 * 1024
MAX_FILES = 2000
SAFE_PATH = re.compile(r'^[A-Za-z0-9_ .@+/-]+$')


def safe_path(path):
    if (not isinstance(path, str) or len(path) > 240 or not SAFE_PATH.fullmatch(path)
            or path.startswith('/') or len(path.split('/')) > 12
            or any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in path.split('/'))):
        raise ValueError('Unsafe package path')
    return path


def json_object(raw):
    if len(raw) > 1024 * 1024:
        raise ValueError('JSON metadata too large')
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError('JSON object required')
    return result


def dependency_key(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid H5P dependency')
    name = value.get('machineName')
    versions = [str(value.get(k)) for k in ('majorVersion', 'minorVersion')]
    if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9.]{0,99}', name)
            or any(not re.fullmatch(r'[0-9]{1,4}', v) for v in versions)):
        raise ValueError('Invalid H5P library identity')
    return name + '-' + '.'.join(versions)


def validate_h5p(files):
    config = json_object(files.get('h5p.json', b''))
    dependencies = config.get('preloadedDependencies')
    if not isinstance(dependencies, list) or not 1 <= len(dependencies) <= 64:
        raise ValueError('Invalid H5P runtime dependencies')
    keys = [dependency_key(d) for d in dependencies]
    if (config.get('mainLibrary') != 'H5P.TrueFalse' or 'H5P.TrueFalse-1.8' not in keys
            or len({d['machineName'] for d in dependencies}) != len(keys)):
        raise ValueError('Only H5P TrueFalse 1.8 is qualified')
    graph = {}
    for key in keys:
        library = json_object(files.get(key + '/library.json', b''))
        if dependency_key(library) != key:
            raise ValueError('H5P library identity mismatch')
        if key == 'H5P.TrueFalse-1.8' and not library.get('preloadedJs'):
            raise ValueError('Missing H5P main runtime')
        for kind in ('preloadedJs', 'preloadedCss'):
            assets = library.get(kind, [])
            if not isinstance(assets, list):
                raise ValueError('Invalid H5P assets')
            for asset in assets:
                if not isinstance(asset, dict):
                    raise ValueError('Invalid H5P asset')
                path = key + '/' + safe_path(asset.get('path'))
                if path not in files:
                    raise ValueError('Missing H5P runtime asset')
        nested = library.get('preloadedDependencies', [])
        if not isinstance(nested, list):
            raise ValueError('Invalid H5P dependencies')
        graph[key] = [dependency_key(d) for d in nested]
        if not set(graph[key]) <= set(keys):
            raise ValueError('Incomplete H5P runtime dependency list')
    def visit(key, visiting, done):
        if key in visiting:
            raise ValueError('Cyclic H5P dependencies')
        if key not in done:
            for child in graph[key]:
                visit(child, visiting | {key}, done)
            done.add(key)
    done = set()
    for key in keys:
        visit(key, set(), done)
    content = json_object(files.get('content/content.json', b''))
    if (type(content.get('correct')) is not str or content['correct'] not in ('true', 'false')
            or not isinstance(content.get('question'), str) or not content['question'].strip()):
        raise ValueError('Invalid TrueFalse content')


def parse_package(raw, kind):
    if not raw or len(raw) > MAX_ARCHIVE or kind not in ('h5p', 'scorm12'):
        raise ValueError('Unsupported or oversized archive')
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        infos = archive.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_TOTAL:
            raise ValueError('Archive limits exceeded')
        files, seen = {}, set()
        for info in infos:
            path = safe_path(info.filename.rstrip('/') if info.is_dir() else info.filename)
            mode = stat.S_IFMT(info.external_attr >> 16)
            if (path.casefold() in seen or info.flag_bits & 1
                    or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    or info.file_size > MAX_FILE or info.file_size > max(1, info.compress_size) * 200):
                raise ValueError('Unsafe or excessive archive entry')
            seen.add(path.casefold())
            if info.is_dir():
                continue
            if path.lower().endswith(('.zip', '.h5p', '.jar', '.gz', '.7z')):
                raise ValueError('Nested archives are not supported')
            with archive.open(info) as stream:
                data = stream.read(MAX_FILE + 1)
            if len(data) != info.file_size or len(data) > MAX_FILE:
                raise ValueError('Invalid entry size')
            files[path] = data
        if kind == 'scorm12':
            manifest = files.get('imsmanifest.xml', b'')
            if len(manifest) > 1024 * 1024 or b'<!DOCTYPE' in manifest.upper() or b'<!ENTITY' in manifest.upper():
                raise ValueError('Unsafe manifest')
            root = etree.fromstring(manifest, etree.XMLParser(resolve_entities=False, no_network=True))
            if root.getroottree().docinfo.doctype:
                raise ValueError('Unsafe manifest')
            versions = root.xpath('//*[local-name()="schemaversion"]/text()')
            resources = root.xpath('//*[local-name()="resource"]')
            if versions != ['1.2'] or len(resources) != 1:
                raise ValueError('Only SCORM 1.2 single SCO is supported')
            resource = resources[0]
            if not any(k.lower().endswith('scormtype') and v == 'sco' for k, v in resource.attrib.items()):
                raise ValueError('A SCO resource is required')
            entry = safe_path(resource.get('href', ''))
            if entry not in files or not entry.lower().endswith(('.html', '.htm')):
                raise ValueError('Missing local HTML entry point')
            for node in root.xpath('//*[local-name()="file"]'):
                if safe_path(node.get('href', '')) not in files:
                    raise ValueError('Missing manifest file')
        else:
            validate_h5p(files)
            entry = 'h5p.json'
        return {'sha256': hashlib.sha256(raw).hexdigest(), 'entrypoint': entry, 'files': files}
    except (zipfile.BadZipFile, RuntimeError, KeyError, TypeError, json.JSONDecodeError, etree.XMLSyntaxError, UnicodeError, RecursionError, zlib.error, EOFError) as error:
        raise ValueError('Invalid package archive or manifest') from error
