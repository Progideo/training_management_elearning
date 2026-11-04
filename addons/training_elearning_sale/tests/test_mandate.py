"""Real mandate and HTTP boundaries, without a portal ORM grant on sale evidence."""

from datetime import timedelta
from unittest.mock import patch
import re
import json
from odoo import fields, Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, Form, new_test_user, tagged
from .test_sale import SalesCase


class MandateCase(SalesCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.representative = new_test_user(
            cls.env, login="fictional_enterprise_representative", groups="base.group_portal"
        )
        cls.peer = new_test_user(cls.env, login="fictional_enterprise_peer", groups="base.group_portal")

    def prepared(self):
        course, slide, product = self.offer()
        order, line = self.order(product, 2)
        order.action_confirm()
        return course, slide, order, line

    def mandate(self, line, user=None, assign=True):
        record = (
            self.env["training.elearning.sale.mandate"]
            .with_user(self.manager)
            .create(
                {
                    "line_id": line.id,
                    "user_id": (user or self.representative).id,
                    "valid_until": fields.Datetime.now() + timedelta(days=700),
                    "can_assign": assign,
                    "beneficiary_ids": [Command.set((self.learner.partner_id | self.other.partner_id).ids)],
                    "reason": "Fictional explicit purchase mandate",
                }
            )
        )
        record.action_grant()
        return record

    def service(self, user=None):
        return self.env["training.elearning.company.service"].with_user(user or self.representative)


@tagged("post_install", "-at_install")
class TestEnterpriseMandates(MandateCase):
    def test_prepared_seat_can_be_finalized_when_no_free_seat_remains(self):
        _, _, _, line = self.prepared()
        line.write({"product_uom_qty": 1})
        seat = self.seat(line)
        line.action_learning_authorize("Fictional prepared beneficiary verified")
        mandate = self.mandate(line)
        data = self.service()._view(mandate.id)
        self.assertEqual(data["remaining"], 0)
        self.assertEqual(
            data["beneficiaries"], [{"id": self.learner.partner_id.id, "name": self.learner.partner_id.name}]
        )
        self.service()._assign(mandate.id, self.learner.partner_id.id)
        self.assertTrue(seat.activated_at)
        self.assertEqual(seat.assigned_by, self.representative)
        self.assertEqual(line.learning_allocation_ids, seat)

    def test_company_boundary_and_unforgeable_mandate_and_assignment_audit(self):
        _, _, _, line = self.prepared()
        mandate = self.mandate(line)
        with self.assertRaises(AccessError):
            self.env["training.elearning.sale.mandate"].with_user(self.manager).create(
                {
                    "line_id": line.id,
                    "user_id": self.peer.id,
                    "valid_until": fields.Datetime.now() + timedelta(days=30),
                    "reason": "Fictional forged active mandate",
                    "state": "active",
                }
            )
        with self.assertRaises(AccessError):
            self.env["training.elearning.sale.mandate"].with_user(self.manager).with_context(
                default_granted_at=False
            ).create(
                {
                    "line_id": line.id,
                    "user_id": self.peer.id,
                    "valid_until": fields.Datetime.now() + timedelta(days=30),
                    "reason": "Fictional forged metadata",
                }
            )
        foreign = self.env["res.company"].create({"name": "Fictional other operator"})
        representative = new_test_user(
            self.env,
            login="fictional_foreign_representative",
            groups="base.group_portal",
            company_id=foreign.id,
            company_ids=[Command.set(foreign.ids)],
        )
        with self.assertRaises((AccessError, ValidationError)):
            self.mandate(line, representative)
        with self.assertRaises(AccessError):
            self.service(representative)._view(mandate.id)
        line.action_learning_authorize("Fictional payment checked")
        self.service()._assign(mandate.id, self.learner.partner_id.id)
        seat = self.env["training.elearning.sale.allocation"].search([("line_id", "=", line.id)])
        with self.assertRaises(AccessError):
            seat.with_user(self.manager).write({"assigned_by": self.manager.id})

    def test_native_form_prepares_readonly_state_and_explicit_grant(self):
        _, _, _, line = self.prepared()
        with Form(self.env["training.elearning.sale.mandate"].with_user(self.manager)) as form:
            form.line_id = line
            form.user_id = self.representative
            form.valid_until = fields.Datetime.now() + timedelta(days=30)
            form.reason = "Fictional explicit view mandate"
        form.record.action_grant()
        self.assertEqual(form.record.state, "active")
        self.assertFalse(self.service()._view(form.record.id)["assignable"])

    def test_only_named_purchase_no_company_or_email_inference_and_no_orm_acl(self):
        course, slide, order, line = self.prepared()
        mandate = self.mandate(line)
        _, _, other_order, other_line = self.prepared()
        other_mandate = self.mandate(other_line, self.peer)
        self.representative.partner_id.parent_id = self.buyer
        self.peer.partner_id.parent_id = self.buyer
        self.assertEqual([d["id"] for d in self.service()._list()], [mandate.id])
        self.assertEqual([d["id"] for d in self.service(self.peer)._list()], [other_mandate.id])
        with self.assertRaises(AccessError):
            self.service()._view(other_mandate.id)
        for record in (mandate, line, self.seat(line)):
            with self.assertRaises(AccessError):
                record.with_user(self.representative).read()
        with self.assertRaises(AccessError):
            mandate.with_user(self.representative).action_grant()
        self.assertFalse(self.representative.has_group("training_elearning_sale.group_learning_sales_manager"))

    def test_assignment_needs_authorized_line_whitelist_and_traces_real_actor(self):
        course, slide, order, line = self.prepared()
        mandate = self.mandate(line)
        with self.assertRaises(AccessError):
            self.service()._assign(mandate.id, self.learner.partner_id.id)
        line.action_learning_authorize("Fictional verified company purchase")
        with self.assertRaises(AccessError):
            self.service()._assign(mandate.id, self.peer.partner_id.id)
        self.service()._assign(mandate.id, self.learner.partner_id.id)
        seat = self.env["training.elearning.sale.allocation"].search([("line_id", "=", line.id)])
        self.assertEqual(seat.assigned_by, self.representative)
        self.assertEqual(seat.assigned_mandate_id, mandate)
        self.assertTrue(seat.activated_at)
        end, mail = seat.access_ends_at, seat.notification_mail_id
        self.service()._assign(mandate.id, self.learner.partner_id.id)
        self.assertEqual(seat.access_ends_at, end)
        self.assertEqual(seat.notification_mail_id, mail)
        self.assertEqual(self.env["training.elearning.sale.allocation"].search_count([("line_id", "=", line.id)]), 1)
        attempt = (
            self.env["training.elearning.exam.service"].with_user(self.learner)._start(seat.membership_id.id, slide.id)
        )
        with self.assertRaises(AccessError):
            self.env["training.elearning.exam.service"].with_user(self.representative)._result(attempt)
        data = self.service()._view(mandate.id)
        self.assertEqual(set(data["rows"][0]), {"beneficiary", "start", "end", "state"})
        for word in ("score", "attempt", "answers", "membership_id", "activity_ids", "notification_mail_id"):
            self.assertNotIn(word, str(data).lower())
        view = self.mandate(line, self.peer, assign=False)
        with self.assertRaises(AccessError):
            self.service(self.peer)._assign(view.id, self.other.partner_id.id)

    def test_revocation_expiry_issuer_withdrawal_and_no_later_funder_disclosure(self):
        course, slide, order, line = self.prepared()
        line.action_learning_authorize("Fictional verification")
        mandate = self.mandate(line)
        self.service()._assign(mandate.id, self.learner.partner_id.id)
        seat = self.env["training.elearning.sale.allocation"].search([("line_id", "=", line.id)])
        # A later grant can extend the membership, but never the purchased dates shown here.
        old_end = seat.access_ends_at
        seat.membership_id.with_user(self.manager).action_learning_activate(
            old_end + timedelta(days=120), self.learner.id, "Fictional later funding"
        )
        with patch.object(fields.Datetime, "now", return_value=old_end + timedelta(days=1)):
            row = self.service()._view(mandate.id)["rows"][0]
            self.assertEqual(row["end"], old_end)
            self.assertEqual(row["state"], "Période financée terminée")
        with patch.object(fields.Datetime, "now", return_value=self.service()._ends_at(mandate.sudo())):
            with self.assertRaises(AccessError):
                self.service()._view(mandate.id)
        with self.assertRaises(AccessError):
            mandate.write({"can_assign": False})
        mandate.write({"revocation_reason": "Fictional mandate withdrawal"})
        mandate.action_revoke()
        with self.assertRaises(AccessError):
            self.service()._view(mandate.id)
        with self.assertRaises(AccessError):
            self.service()._assign(mandate.id, self.other.partner_id.id)
        self.assertEqual(seat.membership_id.learning_state, "active")
        other = self.mandate(line, self.peer)
        self.manager.active = False
        with self.assertRaises(AccessError):
            self.service(self.peer)._view(other.id)

    def test_missing_account_is_reserved_for_coordination_without_identity_disclosure(self):
        course, slide, order, line = self.prepared()
        line.action_learning_authorize("Fictional verification")
        contact = self.env["res.partner"].create(
            {"name": "Fictional validated no-account beneficiary", "email": "fictional-pending@example.invalid"}
        )
        mandate = (
            self.env["training.elearning.sale.mandate"]
            .with_user(self.manager)
            .create(
                {
                    "line_id": line.id,
                    "user_id": self.representative.id,
                    "valid_until": fields.Datetime.now() + timedelta(days=20),
                    "can_assign": True,
                    "beneficiary_ids": [Command.set(contact.ids)],
                    "reason": "Fictional validated roster",
                }
            )
        )
        mandate.action_grant()
        self.service()._assign(mandate.id, contact.id)
        seat = self.env["training.elearning.sale.allocation"].search([("line_id", "=", line.id)])
        self.assertFalse(seat.activated_at)
        self.assertTrue(seat.activity_ids)
        self.service()._assign(mandate.id, contact.id)
        self.assertEqual(len(seat.activity_ids), 1)
        self.assertEqual(self.service()._view(mandate.id)["rows"][0]["state"], "En attente de finalisation")


@tagged("post_install", "-at_install")
class TestEnterprisePortal(MandateCase, HttpCase):
    def test_http_isolation_csrf_replay_revoke_and_private_grant(self):
        course, slide, order, line = self.prepared()
        line.action_learning_authorize("Fictional verification")
        mandate = self.mandate(line)
        self.authenticate(self.representative.login, self.representative.login)
        counters = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"counters": {"learning_purchases_count": "client_category"}},
            "id": 1,
        }
        response = self.url_open(
            "/my/counters", data=json.dumps(counters), headers={"Content-Type": "application/json"}
        )
        self.assertEqual(response.json()["result"]["learning_purchases_count"], 1)
        page = self.url_open("/my/learning-purchases/%s" % mandate.id)
        self.assertEqual(page.status_code, 200)
        self.assertIn("no-store", page.headers["Cache-Control"])
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        path = "/my/learning-purchases/%s/assign" % mandate.id
        self.assertEqual(self.url_open(path, data={"beneficiary": self.learner.partner_id.id}).status_code, 400)
        self.assertEqual(
            self.url_open(path, data={"csrf_token": token, "beneficiary": self.peer.partner_id.id}).status_code, 404
        )
        self.assertEqual(
            self.url_open(path, data={"csrf_token": token, "beneficiary": self.learner.partner_id.id}).status_code, 200
        )
        self.assertEqual(
            self.url_open(path, data={"csrf_token": token, "beneficiary": self.learner.partner_id.id}).status_code, 200
        )
        seat = self.env["training.elearning.sale.allocation"].search([("line_id", "=", line.id)])
        self.assertEqual(len(seat), 1)
        self.assertEqual(self.url_open("/my/learning/%s" % seat.membership_id.id).status_code, 404)
        self.authenticate(self.peer.login, self.peer.login)
        self.assertEqual(self.url_open("/my/learning-purchases/%s" % mandate.id).status_code, 404)
        self.authenticate(self.representative.login, self.representative.login)
        mandate.write({"revocation_reason": "Fictional immediate withdrawal"})
        mandate.action_revoke()
        self.assertEqual(self.url_open("/my/learning-purchases/%s" % mandate.id).status_code, 404)
        response = self.url_open(
            "/my/counters", data=json.dumps(counters), headers={"Content-Type": "application/json"}
        )
        self.assertEqual(response.json()["result"]["learning_purchases_count"], 0)
