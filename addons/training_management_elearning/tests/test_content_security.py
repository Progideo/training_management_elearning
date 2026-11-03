import io
import json
import stat
import zipfile
from odoo.tests import TransactionCase, tagged, new_test_user
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.misc import limited_field_access_token
from ..services.archive import parse_package

MANIFEST = b'''<manifest xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"><metadata><schemaversion>1.2</schemaversion></metadata><resources><resource identifier="sco" adlcp:scormtype="sco" href="index.html"><file href="index.html"/></resource></resources></manifest>'''


def package(extra=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in {'imsmanifest.xml': MANIFEST, 'index.html': b'<p>Fictional SCO</p>', **(extra or {})}.items():
            archive.writestr(name, data)
    return stream.getvalue()


class ContentCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(cls.env, login='e01_author', groups='training_management_elearning.group_elearning_author')
        cls.coord = new_test_user(cls.env, login='e01_coord', groups='training_management.group_training_coordinator')
        cls.portal = new_test_user(cls.env, login='e01_portal', groups='base.group_portal')
        cls.resource = cls.env['training.elearning.resource'].with_user(cls.author).create({'name':'Fictional SCORM', 'format':'scorm12'})
        cls.env['ir.config_parameter'].set_str('training_elearning.portal_origin', 'http://127.0.0.1:18269')
        cls.env['ir.config_parameter'].set_str('training_elearning.content_origin', 'http://localhost:18270')

    def version(self):
        return self.env['training.elearning.version'].with_user(self.author)._import(self.resource, '1', package(), 'Fictional', 'Test')


@tagged('post_install', '-at_install')
class TestContentSecurity(ContentCase):
    def test_hostile_archives(self):
        for name in ('../escape.js', '/absolute', 'a/../b', 'a\\b', 'a//b', 'a%2fb', 'nested.zip'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse_package(package({name:b'bad'}), 'scorm12')
        with self.assertRaises(ValueError):
            parse_package(package({'large.txt': b'a' * 100000}), 'scorm12')
        with self.assertRaises(ValueError):
            parse_package(package({'INDEX.HTML': b'collision'}), 'scorm12')
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            info=zipfile.ZipInfo('link');info.external_attr=(stat.S_IFLNK | 0o777)<<16
            archive.writestr(info,'/etc/passwd')
        with self.assertRaises(ValueError):
            parse_package(stream.getvalue(), 'scorm12')
        with self.assertRaises(ValueError):
            parse_package(package({'imsmanifest.xml':b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><x>&x;</x>'}), 'scorm12')

    def test_h5p_version_numbers_from_export(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('h5p.json', json.dumps({'mainLibrary':'H5P.TrueFalse', 'preloadedDependencies':[{'machineName':'H5P.TrueFalse','majorVersion':'1','minorVersion':'8'}]}))
            archive.writestr('content/content.json', json.dumps({'correct':'true','question':'Fictional question'}))
            archive.writestr('H5P.TrueFalse-1.8/library.json', json.dumps({'machineName':'H5P.TrueFalse','majorVersion':1,'minorVersion':8,'preloadedJs':[{'path':'test.js'}]}))
            archive.writestr('H5P.TrueFalse-1.8/test.js', '// Fictional runtime file')
        self.assertEqual(parse_package(stream.getvalue(), 'h5p')['entrypoint'], 'h5p.json')

    def test_immutable_bytes_and_native_bypass(self):
        version = self.version()
        file = self.env['training.elearning.file'].sudo().search([('version_id','=',version.id)],limit=1)
        for actor in (self.author, self.coord, self.portal):
            with self.assertRaises(AccessError):
                file.with_user(actor).read(['data'])
        token = limited_field_access_token(file, 'data', scope='binary')
        binary = self.env['ir.binary'].with_user(self.portal)
        resolved = binary._find_record(res_model=file._name,res_id=file.id,field='data',access_token=token)
        with self.assertRaises(AccessError):
            binary._get_stream_from(resolved, 'data')
        with self.assertRaises(ValidationError):
            version.write({'entrypoint':'hostile.html'})
        # D32: the habilitated author now publishes directly.
        version.action_publish()
        with self.assertRaises(ValidationError):
            version.with_user(self.coord).action_publish()
        self.assertEqual(version.state, 'published')

    def test_shared_library_author_preview_without_tm_role(self):
        author = new_test_user(self.env, login='shared_library_preview_author',
                               groups='training_interactive.group_interactive_author')
        version = self.version()
        self.assertFalse(author.has_group('training_management.group_training_coordinator'))
        self.assertFalse(author.has_group('training_management_elearning.group_elearning_author'))
        service = self.env['training.elearning.lease'].with_user(author)
        lease, token = service._issue(version.with_user(author))
        self.assertEqual(service._resolve(token), lease)
        self.assertEqual(lease.sudo().version_id, version)
        self.assertEqual(version.resource_id, self.resource)

    def test_lease_current_rights_and_withdrawal(self):
        version = self.version()
        service = self.env['training.elearning.lease'].with_user(self.author)
        lease, token = service._issue(version)
        self.assertEqual(service._resolve(token), lease)
        with self.assertRaises(AccessError):
            self.env['training.elearning.lease'].with_user(self.portal)._issue(version)
        self.author.active = False
        with self.assertRaises(AccessError):
            service._resolve(token)
        self.author.active = True
        version.with_user(self.coord)._withdraw('Fictional security withdrawal')
        with self.assertRaises(AccessError):
            service._resolve(token)
