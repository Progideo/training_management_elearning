"""The access email is now written in English with a French translation. It is `noupdate`:
reload this template once from the module data, with its French translation (the
notification cron of the same file is left unchanged)."""

import io

from lxml import etree
from odoo.tools import file_path
from odoo.tools.convert import convert_xml_import
from odoo.tools.translate import TranslationImporter

MODULE = "training_elearning_sale"


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    path = file_path(f"{MODULE}/data/mail.xml")
    root = etree.Element("odoo")
    root.append(etree.parse(path).find(".//record[@id='access_notification']"))
    stream = io.BytesIO(etree.tostring(root))
    stream.name = path
    convert_xml_import(env, MODULE, stream, {}, "init", True)
    importer = TranslationImporter(cr, verbose=False)
    for code, _name in env["res.lang"].get_installed():
        if code.split("_")[0] == "fr":
            importer.load_file(
                file_path(f"{MODULE}/i18n/fr.po"),
                code,
                xmlids=[f"{MODULE}.access_notification"],
            )
    importer.save(overwrite=True, force_overwrite=True)
