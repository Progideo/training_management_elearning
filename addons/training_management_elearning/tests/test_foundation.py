# SPDX-License-Identifier: LGPL-3.0-only
from odoo.tests import TransactionCase, new_test_user, tagged, Form
from odoo.exceptions import AccessError, ValidationError
from odoo.modules.module import get_manifest


@tagged('post_install', '-at_install')
class TestFoundation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(cls.env, login='e00_author', groups='training_management_elearning.group_elearning_author')
        cls.portal = new_test_user(cls.env, login='e00_portal', groups='base.group_portal')
        cls.other = cls.env['res.company'].create({'name': 'E00 fictional other company'})
        cls.Resource = cls.env['training.elearning.resource']

    def test_native_form_identity_and_archive(self):
        with Form(self.Resource.with_user(self.author)) as form:
            form.name = 'Fictional resource'
            form.format = 'h5p'
        resource = form.record
        identifier = resource.identifier
        resource.write({'name': 'Revised title', 'active': False})
        self.assertEqual(resource.identifier, identifier)
        for values in ({'identifier': 'replacement'}, {'company_id': self.other.id}, {'format': 'scorm12'}):
            with self.assertRaises(ValidationError):
                resource.write(values)
        with self.assertRaises(ValidationError):
            resource.sudo().unlink()

    def test_company_and_portal_boundaries(self):
        resource = self.Resource.create({'name': 'Private B', 'format': 'h5p', 'company_id': self.other.id})
        self.assertFalse(self.Resource.with_user(self.author).search([('id', '=', resource.id)]))
        with self.assertRaises(AccessError):
            resource.with_user(self.author).read(['name'])
        with self.assertRaises(AccessError):
            self.Resource.with_user(self.portal).search([])
        with self.assertRaises(AccessError):
            self.Resource.with_user(self.author).create({'name': 'Forbidden B', 'format': 'h5p', 'company_id': self.other.id})
        self.assertFalse(self.author.has_group('training_management.group_training_coordinator'))
        self.assertFalse(self.author.has_group('website.group_website_designer'))
        self.assertFalse(self.author.has_group('base.group_system'))

    def test_no_competing_learning_or_runtime(self):
        # The November 3 architecture permits the native autonomous app on
        # this database, while this TM adapter must not depend on it.
        depends = get_manifest('training_management_elearning')['depends']
        self.assertNotIn('website_slides', depends)
        self.assertNotIn('training_elearning', depends)
        if 'slide.channel' in self.env.registry:
            self.assertEqual(self.env.ref('website_slides.model_slide_channel').model, 'slide.channel')
        self.assertNotIn('runtime_formative', dict(self.env['training.learning.activity']._fields['criterion']._description_selection(self.env)))
        self.assertNotIn('data', self.Resource._fields)
