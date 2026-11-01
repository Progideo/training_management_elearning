"""Bounded archive validation. Never extracts untrusted paths to a filesystem."""
import hashlib
import io
import json
import re
import stat
import zipfile
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
            manifest = files.get('h5p.json', b'')
            if len(manifest) > 1024 * 1024:
                raise ValueError('Manifest too large')
            config = json.loads(manifest)
            dependencies = config.get('preloadedDependencies', [])
            if (config.get('mainLibrary') != 'H5P.TrueFalse'
                    or not any(d.get('machineName') == 'H5P.TrueFalse' and str(d.get('majorVersion')) == '1'
                               and str(d.get('minorVersion')) == '8' for d in dependencies)):
                raise ValueError('Only H5P TrueFalse 1.8 is qualified')
            content = json.loads(files.get('content/content.json', b''))
            if type(content.get('correct')) is not str or content['correct'] not in ('true', 'false'):
                raise ValueError('Invalid TrueFalse content')
            entry = 'h5p.json'
        return {'sha256': hashlib.sha256(raw).hexdigest(), 'entrypoint': entry, 'files': files}
    except (zipfile.BadZipFile, RuntimeError, KeyError, TypeError, json.JSONDecodeError, etree.XMLSyntaxError) as error:
        raise ValueError('Invalid package archive or manifest') from error
