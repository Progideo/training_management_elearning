import json
import re
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from .test_attempt import RuntimeCase
from .test_content_security import package


class HostCase(RuntimeCase, HttpCase):
    def setUp(self):
        super().setUp()
        params = self.env['ir.config_parameter'].sudo()
        self.portal_origin = 'http://127.0.0.1:%s' % self.http_port()
        self.content_origin = 'http://localhost:%s' % self.http_port()
        params.set_str('training_elearning.portal_origin', self.portal_origin)
        params.set_str('training_elearning.content_origin', self.content_origin)
        self.env.flush_all()


@tagged('post_install', '-at_install')
class TestPortalHost(HostCase):
    def test_participant_opens_entry_with_or_without_website(self):
        enrollment, usage = self.setup_runtime()
        self.env.flush_all()
        self.authenticate(self.portal.login, self.portal.login)
        link = '/training/interactive/%s/%s' % (enrollment.id, usage.id)
        self.assertIn(link, self.url_open('/my/trainings/%s' % enrollment.id).text)
        response = self.url_open(link)
        self.assertEqual(response.status_code, 200)
        self.assertIn(link + '/start', response.text)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text).group(1)
        key = re.search(r'name="request_key"[^>]*value="([^"]+)"', response.text).group(1)
        started = self.url_open(link + '/start', data={'csrf_token': token, 'request_key': key})
        self.assertEqual(started.status_code, 200)
        self.assertIn('/training/interactive/attempt/', started.url)

    def test_content_host_refuses_native_routes_even_without_proxy(self):
        for path in ('/web/login', '/my', '/formations', '/', '/web/image/res.partner/1/avatar_128', '/no-such-page'):
            with self.subTest(path=path):
                response = self.url_open(self.content_origin + path, allow_redirects=False)
                self.assertEqual(response.status_code, 403)
                self.assertNotIn('session_id=', response.headers.get('Set-Cookie', ''))
        self.assertEqual(self.url_open(self.content_origin + '/tm-content/' + 'a' * 43 + '/launch').status_code, 403)
        self.assertEqual(self.url_open(self.portal_origin + '/web/login').status_code, 200)

    def test_one_host_named_twice_does_not_lock_the_portal(self):
        self.env['ir.config_parameter'].sudo().set_str('training_elearning.content_origin', self.portal_origin)
        self.env.flush_all()
        self.assertEqual(self.url_open(self.portal_origin + '/web/login').status_code, 200)


@tagged('post_install', '-at_install')
class TestPreviewRenewal(HostCase):
    def preview(self):
        resource = self.env['training.elearning.resource'].with_user(self.coordinator).create({'name': 'Preview', 'format': 'scorm12'})
        version = self.env['training.elearning.version'].with_user(self.coordinator)._import(resource, '1', package(), 'Test', 'Fictional')
        lease, _token = self.env['training.elearning.lease'].with_user(self.coordinator)._issue(version.with_user(self.coordinator))
        self.env.flush_all()
        return version, lease

    def renew(self, version, lease_id, csrf):
        return self.url_open('/training/interactive/preview/%s/renew' % version.id, data={'csrf_token': csrf, 'lease': lease_id})

    def test_author_renews_own_preview_only(self):
        version, lease = self.preview()
        self.authenticate(self.coordinator.login, self.coordinator.login)
        page = self.url_open('/training/interactive/preview/%s' % version.id)
        config = json.loads(re.search(r'<script id="config" type="application/json">(.*?)</script>', page.text).group(1))
        self.assertEqual(config['renew'], '/training/interactive/preview/%s/renew' % version.id)
        self.env.cr.execute("UPDATE training_elearning_lease SET expires_at = expires_at - interval '1 minute' WHERE id = %s RETURNING expires_at", [lease.id])
        shortened = self.env.cr.fetchone()[0]
        lease.invalidate_recordset()
        self.assertEqual(self.renew(version, lease.id, config['csrf']).status_code, 200)
        lease.invalidate_recordset()
        self.assertGreater(lease.sudo().expires_at, shortened)
        self.assertEqual(self.renew(version, lease.id + 100000, config['csrf']).status_code, 403)

    def test_withdrawn_preview_is_not_renewed(self):
        version, lease = self.preview()
        version.with_user(self.coordinator)._withdraw('Fictional withdrawal')
        with self.assertRaises(AccessError):
            lease.sudo()._renew()

    def test_participant_cannot_renew_someone_elses_preview(self):
        version, lease = self.preview()
        self.authenticate(self.portal.login, self.portal.login)
        csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', self.url_open('/my/training-signature').text).group(1)
        self.assertEqual(self.renew(version, lease.id, csrf).status_code, 403)
