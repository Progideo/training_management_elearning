from odoo.tests import Form, tagged
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.binary import BinaryBytes
from odoo.addons.training_management.tests.test_learning import LearningCase
from .test_content_security import package


@tagged('post_install', '-at_install')
class TestEditorial(LearningCase):
    def test_reuse_frozen_versions_rules_and_history(self):
        resource=self.env['training.elearning.resource'].with_user(self.coordinator).create({'name':'Reusable SCO','format':'scorm12'})
        wizard=self.env['training.elearning.import'].with_user(self.coordinator).create({'resource_id':resource.id,'number':'1','data':BinaryBytes(package()),'filename':'sco.zip','license_note':'Fictional','provenance':'Tests'})
        action=wizard.action_import()
        version=self.env['training.elearning.version'].with_user(self.coordinator).browse(action['res_id'])
        version.action_publish()
        with Form(self.env['training.elearning.assignment'].with_user(self.coordinator)) as form:
            form.name='Reusable activity';form.program_id=self.program;form.version_id=version
            form.objective='Practice';form.rule='score';form.threshold=70
        assignment=form.record
        assignment.action_validate()
        first, second=self.delivery(),self.delivery()
        usages=assignment._apply(first|second)
        self.assertEqual(len(usages),2)
        self.assertEqual(usages.version_id,version)
        self.assertEqual(len(usages.activity_id),2)
        self.assertEqual(assignment._apply(first).id,usages.filtered(lambda u:u.delivery_id==first).id)
        with self.assertRaises(ValidationError): assignment.write({'threshold':90})
        with self.assertRaises(ValidationError): usages.activity_id.write({'criterion':'validation'})
        enrollment=self.opened(first)
        self.assertFalse(self.service()._complete(enrollment,usages.filtered(lambda u:u.delivery_id==first).activity_id))
        v2=self.env['training.elearning.version'].with_user(self.coordinator)._import(resource,'2',package(),'Fictional','Tests')
        v2.action_publish()
        self.assertEqual(usages.version_id,version)
        resource.active=False
        with self.assertRaises(ValidationError): assignment._apply(self.delivery())
        self.assertEqual(usages.version_id,version)
        with self.assertRaises(AccessError): self.env['training.elearning.assignment'].with_user(self.portal).search([])
