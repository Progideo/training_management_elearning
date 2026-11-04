"""Native whole/partial path purchases, explicit mandates and single course progression."""

from unittest.mock import patch
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError, LockError
from odoo.tests import new_test_user, tagged
from odoo.addons.training_elearning.tests.test_path import PathCase


@tagged("post_install", "-at_install")
class TestPathSales(PathCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = new_test_user(
            cls.env,
            login="fictional_path_sales_manager",
            groups="training_elearning_sale.group_learning_sales_manager",
        )
        cls.representative = new_test_user(cls.env, login="fictional_path_representative", groups="base.group_portal")
        cls.buyer = cls.env["res.partner"].create({"name": "Fictional curriculum purchaser", "is_company": True})

    def product(self, path, courses=None):
        values = {
            "name": "Fictional curriculum offer",
            "type": "service",
            "learning_path_id": path.id,
        }
        if courses is not None:
            values["learning_path_course_ids"] = [Command.set(courses.ids)]
        return self.env["product.product"].with_user(self.commercial).create(values)

    def order(self, product, qty=1, kind="initial", user=None):
        order = (
            self.env["sale.order"]
            .with_user(user or self.commercial)
            .create(
                {
                    "partner_id": self.buyer.id,
                    "order_line": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_uom_qty": qty,
                                "learning_purchase_kind": kind,
                            }
                        )
                    ],
                }
            )
        )
        return order, order.order_line

    def seat(self, line):
        return (
            self.env["training.elearning.sale.allocation"]
            .with_user(self.commercial)
            .create(
                {
                    "line_id": line.id,
                    "partner_id": self.learner.partner_id.id,
                }
            )
        )

    def test_confirm_authorize_named_seat_and_one_native_membership_per_course(self):
        first, a = self.edition("Fictional whole-path first course")
        second, b = self.edition("Fictional whole-path second course")
        path = self.path([(first, True), (second, True)])
        product = self.product(path)
        order, line = self.order(product)
        order.action_confirm()
        self.assertTrue(line.learning_confirmed_at)
        self.assertEqual(line.learning_plan["included"], path.line_ids.course_id.ids)
        seat = self.seat(line)
        with self.assertRaises(ValidationError):
            seat.action_learning_activate()
        self.assertFalse(seat.path_activation_id)
        line.action_learning_authorize("Fictional path commercial approval")
        seat.action_learning_activate()
        context = seat.path_activation_id
        self.assertEqual(len(context.item_ids.filtered("activated_at")), 2)
        self.assertFalse(seat.membership_id)
        ends = context.item_ids.mapped("access_ends_at")
        seat.action_learning_activate()
        self.assertEqual(seat.path_activation_id, context)
        self.assertEqual(context.item_ids.mapped("access_ends_at"), ends)
        with self.assertRaises(ValidationError):
            self.env["training.elearning.sale.allocation"].with_user(self.commercial).create(
                {"line_id": line.id, "partner_id": self.other.partner_id.id}
            )
        # Another initial purchase contributes rights; it does not create a second progress.
        later = fields.Datetime.now() + timedelta(days=1)
        with patch.object(fields.Datetime, "now", return_value=later):
            next_order, other_line = self.order(product)
            next_order.action_confirm()
            other_line.action_learning_authorize("Fictional distinct path funding")
            other_seat = self.seat(other_line)
            other_seat.action_learning_activate()
        self.assertEqual(other_seat.path_activation_id.registration_id, context.registration_id)
        for course in first | second:
            old_item = context.item_ids.filtered(lambda item: item.course_id == course)
            new_item = other_seat.path_activation_id.item_ids.filtered(lambda item: item.course_id == course)
            self.assertEqual(old_item.membership_id, new_item.membership_id)
            self.assertLess(old_item.access_ends_at, new_item.access_ends_at)
            self.assertEqual(old_item.membership_id.learning_ends_at, new_item.access_ends_at)
        registration = context.registration_id
        service = self.env["training.elearning.service"].with_user(self.learner)
        service._declare(registration._member(first.id).id, a.id)
        service._declare(registration._member(second.id).id, b.id)
        self.assertTrue(registration._summary()["complete"])
        self.assertEqual(
            len(
                self.env["slide.channel.partner"].search(
                    [
                        ("channel_id", "in", (first | second).ids),
                        ("partner_id", "=", self.learner.partner_id.id),
                    ]
                )
            ),
            2,
        )

    def test_partial_offer_uses_expired_acquisition_and_mandate_sees_only_own_period(
        self,
    ):
        first, a = self.edition("Fictional prior path acquisition")
        prior = self.member(first)
        self.env["training.elearning.service"].with_user(self.learner)._declare(prior.id, a.id)
        prior._learning_store({"learning_ends_at": fields.Datetime.now() - timedelta(seconds=1)})
        second, _b = self.edition("Fictional funded partial course", first)
        path = self.path([(first, True), (second, True)])
        product = self.product(path, second)
        order, line = self.order(product)
        order.action_confirm()
        html, _kind = self.env["ir.actions.report"]._render_qweb_html("sale.report_saleorder", [order.id])
        self.assertIn(b"Cours inclus dans cette offre", html)
        self.assertIn(second.name.encode(), html)
        self.assertNotIn(b"PRIVATE LESSON TEXT", html)
        terms = line._learning_offer_terms()
        self.assertTrue(terms["partial"])
        self.assertEqual(terms["courses"], second.mapped("name"))
        line.action_learning_authorize("Fictional partial path approval")
        mandate = (
            self.env["training.elearning.sale.mandate"]
            .with_user(self.commercial)
            .create(
                {
                    "line_id": line.id,
                    "user_id": self.representative.id,
                    "valid_until": fields.Datetime.now() + relativedelta(years=3),
                    "can_assign": True,
                    "beneficiary_ids": [Command.set(self.learner.partner_id.ids)],
                    "reason": "Fictional explicit mandate on partial curriculum purchase",
                }
            )
        )
        mandate.action_grant()
        service = self.env["training.elearning.company.service"].with_user(self.representative)
        model = self.env["training.elearning.sale.allocation"]
        with patch.object(
            type(model),
            "action_learning_activate",
            side_effect=LockError("Fictional concurrent path activation"),
        ):
            service._assign(mandate.id, self.learner.partner_id.id)
        prepared = line.learning_allocation_ids
        self.assertFalse(prepared.activated_at)
        self.assertTrue(prepared.assignment_activity_id)
        service._assign(mandate.id, self.learner.partner_id.id)
        service._assign(mandate.id, self.learner.partner_id.id)
        seat = line.learning_allocation_ids
        self.assertEqual(len(seat), 1)
        self.assertTrue(seat.path_activation_id)
        self.assertFalse(seat.assignment_activity_id)
        item = seat.path_activation_id.item_ids
        self.assertEqual(item.course_id, second)
        self.assertTrue(item.activated_at)
        self.assertLess(prior.learning_ends_at, fields.Datetime.now())
        view = service._view(mandate.id)
        self.assertEqual(view["allocated"], 1)
        self.assertEqual(view["rows"][0]["end"], item.access_ends_at)
        self.assertNotIn("membership_id", view["rows"][0])
        mandate.write({"revocation_reason": "Fictional immediate mandate revocation"})
        mandate.action_revoke()
        with self.assertRaises(AccessError):
            service._view(mandate.id)
        self.env["training.elearning.service"].with_user(self.learner)._membership(item.membership_id.id)

    def test_native_salesperson_copy_uses_configured_path_and_cannot_forge_terms(self):
        course, _a = self.edition("Fictional native copied path course")
        path = self.path([(course, True)])
        product = self.product(path)
        seller = new_test_user(
            self.env,
            login="fictional_path_native_salesperson",
            groups="sales_team.group_sale_salesman",
        )
        order, line = self.order(product, user=seller)
        order.action_confirm()
        self.assertTrue(line.sudo().learning_plan)
        self.assertFalse(line.sudo().learning_authorized_at)
        duplicate = order.copy()
        self.assertEqual(duplicate.order_line.learning_path_id, path)
        self.assertEqual(duplicate.order_line.sudo().learning_path_course_ids, course)
        with self.assertRaises(AccessError):
            course.with_user(seller).read(["name"])
        self.assertFalse(duplicate.order_line.learning_confirmed_at)
        with self.assertRaises(AccessError):
            duplicate.order_line.action_learning_authorize("Fictional unauthorized commercial decision")
        for values in (
            {"learning_path_start_months": 999},
            {"learning_path_course_ids": [Command.clear()]},
        ):
            with self.assertRaises(AccessError):
                self.env["sale.order.line"].with_user(seller).create(
                    {"order_id": duplicate.id, "product_id": product.id, **values}
                )

    def test_accounting_cancellation_does_not_erase_authorized_curriculum_or_acquisitions(
        self,
    ):
        first, a = self.edition("Fictional cancelled-order prerequisite")
        second, _b = self.edition("Fictional previously authorized dependent", first)
        path = self.path([(first, True), (second, True)])
        order, line = self.order(self.product(path))
        order.action_confirm()
        line.action_learning_authorize("Fictional original commercial approval")
        seat = self.seat(line)
        seat.action_learning_activate()
        context = seat.path_activation_id
        member = context.registration_id._member(first.id)
        order.action_cancel()
        self.assertEqual(order.state, "cancel")
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, a.id)
        self.assertTrue(context.item_ids.filtered(lambda item: item.course_id == second).activated_at)
        self.assertEqual(member.completion, 100)
