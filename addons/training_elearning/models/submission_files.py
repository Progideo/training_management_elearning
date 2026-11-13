"""Bounded, non-executing format checks for private practical-work submissions."""

import hashlib
import io
import json
import re
import warnings
import zipfile
from xml.etree import ElementTree

MIB = 1024 * 1024
DEFAULT_EXTENSIONS = "pdf,png,jpg,jpeg,docx,xlsx,pptx,txt,csv"
OFFICE = {
    "docx": (
        "word/document.xml",
        "document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "xlsx": ("xl/workbook.xml", "workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "pptx": (
        "ppt/presentation.xml",
        "presentation",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
}
RASTER = {
    "png": ("PNG", "image/png"),
    "jpg": ("JPEG", "image/jpeg"),
    "jpeg": ("JPEG", "image/jpeg"),
    "webp": ("WEBP", "image/webp"),
    "gif": ("GIF", "image/gif"),
    "bmp": ("BMP", "image/bmp"),
    "tif": ("TIFF", "image/tiff"),
    "tiff": ("TIFF", "image/tiff"),
}
TEXT = {
    "txt": "text/plain",
    "csv": "text/csv",
    "md": "text/markdown",
    "json": "application/json",
    "xml": "application/xml",
}
SUPPORTED = {"pdf", *OFFICE, *RASTER, *TEXT}


class InvalidSubmission(ValueError):
    """A stable cause for the portal; never include file contents in errors."""


def extensions(value):
    values = {part.strip().lower().lstrip(".") for part in (value or "").split(",") if part.strip()}
    if not values or any(not re.fullmatch(r"[a-z0-9]+", part) or part not in SUPPORTED for part in values):
        raise InvalidSubmission("unsupported_extension_configuration")
    return values


def _xml(data, *, root_only=False):
    try:
        text = data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        if "<!doctype" in text.lower() or "<!entity" in text.lower():
            raise InvalidSubmission("xml_entities_not_allowed")
        if root_only:
            stack = []
            root_tag = None
            for event, element in ElementTree.iterparse(io.StringIO(text), events=("start", "end")):
                if event == "start":
                    stack.append(element)
                    if len(stack) > 128:
                        raise InvalidSubmission("xml_structure_limit")
                    if root_tag is None:
                        root_tag = element.tag
                else:
                    stack.pop()
                    if stack:
                        stack[-1].remove(element)
                    element.clear()
            return root_tag
        if len(data) > 4 * MIB:
            raise InvalidSubmission("xml_structure_limit")
        return ElementTree.fromstring(text)
    except (UnicodeError, ElementTree.ParseError) as error:
        raise InvalidSubmission("invalid_xml") from error


def _office(data, extension):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            infos = package.infolist()
            if len(infos) > 2048 or sum(info.file_size for info in infos) > 64 * MIB:
                raise InvalidSubmission("office_expansion_limit")
            seen = set()
            for info in infos:
                path = info.filename
                folded = path.casefold()
                if (
                    not path
                    or path.startswith("/")
                    or "\\" in path
                    or "\x00" in path
                    or info.orig_filename != path
                    or any(part in (".", "..") for part in path.rstrip("/").split("/"))
                    or folded in seen
                    or info.flag_bits & 1
                    or (info.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise InvalidSubmission("invalid_office_package")
                seen.add(folded)
                if (
                    "vbaproject" in folded
                    or "vbadata" in folded
                    or "/activex/" in folded
                    or "/macrosheets/" in folded
                    or "/embeddings/" in folded
                    or folded.endswith((".exe", ".dll", ".com", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi"))
                ):
                    raise InvalidSubmission("macros_or_embedded_executable")
                if info.file_size > max(1024, info.compress_size) * 200:
                    raise InvalidSubmission("office_expansion_limit")
            main, root_name, mimetype = OFFICE[extension]
            if (
                main not in package.namelist()
                or "[Content_Types].xml" not in package.namelist()
                or "_rels/.rels" not in package.namelist()
            ):
                raise InvalidSubmission("office_type_mismatch")
            types = _xml(package.read("[Content_Types].xml"))
            declared = [node.attrib.get("ContentType", "").lower() for node in types]
            if any(
                any(marker in value for marker in ("macroenabled", "vba", "macrosheet", "activex"))
                for value in declared
            ):
                raise InvalidSubmission("macros_or_embedded_executable")
            if not any(
                node.attrib.get("PartName") == "/" + main and node.attrib.get("ContentType", "").startswith(mimetype)
                for node in types
            ):
                raise InvalidSubmission("office_type_mismatch")
            relationships = _xml(package.read("_rels/.rels"))
            if not any(
                node.attrib.get("Target", "").lstrip("/") == main
                and node.attrib.get("Type", "").endswith("/officeDocument")
                and node.attrib.get("TargetMode") != "External"
                for node in relationships
            ):
                raise InvalidSubmission("office_type_mismatch")
            root_tag = _xml(package.read(main), root_only=True)
            if root_tag.rsplit("}", 1)[-1] != root_name:
                raise InvalidSubmission("office_type_mismatch")
            for info in infos:
                if not info.filename.lower().endswith(".rels"):
                    continue
                rels = _xml(package.read(info.filename))
                for relation in rels:
                    relation_type = relation.attrib.get("Type", "").lower()
                    if (
                        "vba" in relation_type
                        or "activex" in relation_type
                        or relation_type.endswith("/control")
                        or relation_type.endswith(("/oleobject", "/package"))
                        or (
                            relation.attrib.get("TargetMode") == "External" and not relation_type.endswith("/hyperlink")
                        )
                    ):
                        raise InvalidSubmission("active_office_relationship")
            return mimetype
    except (zipfile.BadZipFile, KeyError, RuntimeError, OSError, NotImplementedError, EOFError) as error:
        raise InvalidSubmission("invalid_office_package") from error


def _format(data, extension):
    if extension in OFFICE:
        return _office(data, extension)
    if extension in RASTER:
        from PIL import Image, UnidentifiedImageError  # native Odoo dependency

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(io.BytesIO(data))
                if image.format != RASTER[extension][0]:
                    raise InvalidSubmission("image_type_mismatch")
                image.verify()
            return RASTER[extension][1]
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as error:
            raise InvalidSubmission("invalid_image") from error
    if extension == "pdf":
        from odoo.tools.pdf import PdfFileReader  # use the exact native parser

        try:
            if not data.startswith(b"%PDF-"):
                raise InvalidSubmission("invalid_pdf")
            pdf = PdfFileReader(io.BytesIO(data), overwriteWarnings=False)
            if pdf.is_encrypted or not len(pdf.pages):
                raise InvalidSubmission("encrypted_or_empty_pdf")
            return "application/pdf"
        except InvalidSubmission:
            raise
        except Exception as error:  # native PDF libraries expose several parser exceptions
            raise InvalidSubmission("invalid_pdf") from error
    if extension in TEXT:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            try:
                text = data.decode("cp1252")
            except UnicodeError as error:
                raise InvalidSubmission("invalid_text_encoding") from error
        if any(ord(char) < 32 and char not in "\t\r\n\f" for char in text):
            raise InvalidSubmission("binary_file_renamed_as_text")
        if extension == "json":
            try:
                json.loads(text)
            except (ValueError, RecursionError) as error:
                raise InvalidSubmission("invalid_json") from error
        elif extension == "xml":
            _xml(data)
        # CSV has no unique dialect or field-length ceiling. The bounded text
        # check suffices; never interpret formulas or alter csv's global limits.
        return TEXT[extension]
    raise InvalidSubmission("unsupported_file_type")


def validate_files(files, policy):
    allowed = extensions(policy["extensions"])
    if not files or len(files) > policy["files"]:
        raise InvalidSubmission("file_count_limit")
    if sum(len(content) for _name, content in files) > policy["total_mib"] * MIB:
        raise InvalidSubmission("total_size_limit")
    result = []
    for filename, content in files:
        if (
            not isinstance(filename, str)
            or not filename.strip()
            or len(filename) > 240
            or any(char in filename for char in ("/", "\\"))
            or any(ord(char) < 32 or ord(char) == 127 for char in filename)
        ):
            raise InvalidSubmission("invalid_filename")
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in allowed:
            raise InvalidSubmission("file_type_not_allowed")
        if not content or len(content) > policy["file_mib"] * MIB:
            raise InvalidSubmission("single_file_size_limit")
        mimetype = _format(content, extension)
        result.append(
            {
                "name": filename,
                "content": content,
                "mimetype": mimetype,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    return result
