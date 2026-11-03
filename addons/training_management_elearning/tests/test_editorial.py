from lxml import etree

from odoo import Command
from odoo.tests import Form, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import AccessError, UserError, ValidationError
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

    def test_new_assignment_program_picker_and_company_scope(self):
        assignments = self.env['training.elearning.assignment'].with_user(self.coordinator)
        view = etree.fromstring(assignments.get_view(view_type='form')['arch'])
        program_node = view.xpath("//field[@name='program_id']")[0]
        # Match the web client's effective domain before a programme is selected.
        domain_expression = program_node.get('domain') or assignments.fields_get(['program_id'])['program_id']['domain']
        domain = safe_eval(domain_expression, {
            'company_id': False, 'allowed_company_ids': self.coordinator.company_ids.ids,
        }) if isinstance(domain_expression, str) else domain_expression
        programs = self.env['training.program.version'].with_user(self.coordinator)
        self.assertIn(self.program, programs.search(domain))

        foreign_course = self.env['training.course'].create({
            'name': 'Fictional other company course', 'company_id': self.other_company.id,
        })
        foreign_program = self.program.copy({'course_id': foreign_course.id, 'version': 'B-1'})
        self.assertNotIn(foreign_program, programs.search(domain))

        multi = new_test_user(self.env, login='editorial_multi',
            groups='training_management.group_training_coordinator',
            company_id=self.company.id,
            company_ids=[Command.set((self.company | self.other_company).ids)])
        foreign_resources = self.env['training.elearning.resource'].with_user(multi).with_company(self.other_company)
        foreign_resource = foreign_resources.create({'name': 'Other company SCO', 'format': 'scorm12'})
        foreign_version = self.env['training.elearning.version'].with_user(multi)._import(
            foreign_resource, '1', package(), 'Fictional', 'Tests')
        foreign_version.action_publish()
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            assignments.create({
                'name': 'Forbidden programme', 'program_id': foreign_program.id,
                'version_id': foreign_version.id, 'objective': 'Fictional',
            })
        self.assertTrue(view.xpath("//field[@name='company_id']"))
        version_node = view.xpath("//field[@name='version_id']")[0]
        version_domain = safe_eval(version_node.get('domain'), {'company_id': self.company.id})
        self.assertNotIn(foreign_version, self.env['training.elearning.version'].with_user(multi).search(version_domain))
        # Even an operator allowed in both companies cannot mix their objects.
        with self.assertRaises(UserError), self.env.cr.savepoint():
            assignments.with_user(multi).create({
                'name': 'Inconsistent version', 'program_id': self.program.id,
                'version_id': foreign_version.id, 'objective': 'Fictional',
            })
