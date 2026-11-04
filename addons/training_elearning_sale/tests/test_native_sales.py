"""Autonomous sales also operate when the optional Survey adapter is absent."""

from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestNativeCourseSales(TransactionCase):
    def test_article_course_commercial_activation_needs_no_exam(self):
        manager = new_test_user(
            self.env,
            login="fictional_native_sales_manager",
            groups="training_elearning_sale.group_learning_sales_manager",
        )
        learner = new_test_user(self.env, login="fictional_native_sales_learner", groups="base.group_portal")
        catalog = self.env["training.course"].create({"name": "Fictional native-only catalogue"})
        course = (
            self.env["slide.channel"]
            .with_user(manager)
            .create({"name": "Fictional native-only edition", "training_course_id": catalog.id})
        )
        slide = (
            self.env["slide.slide"]
            .with_user(manager)
            .create(
                {
                    "name": "Fictional native-only article",
                    "channel_id": course.id,
                    "slide_category": "article",
                    "html_content": "<p>Fictional native-only learning</p>",
                    "is_published": True,
                }
            )
        )
        course.action_learning_publish()
        product = (
            self.env["product.product"]
            .with_user(manager)
            .create({"name": "Fictional article offer", "type": "service", "learning_channel_id": course.id})
        )
        buyer = self.env["res.partner"].create({"name": "Fictional native course buyer"})
        order = (
            self.env["sale.order"]
            .with_user(manager)
            .create(
                {
                    "partner_id": buyer.id,
                    "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1})],
                }
            )
        )
        order.action_confirm()
        line = order.order_line
        self.assertEqual(line.learning_plan["slides"][0]["kind"], "article")
        line.action_learning_authorize("Fictional authorized native-only sale")
        seat = (
            self.env["training.elearning.sale.allocation"]
            .with_user(manager)
            .create({"line_id": line.id, "partner_id": learner.partner_id.id})
        )
        seat.action_learning_activate()
        member = seat.membership_id
        self.assertEqual(member.learning_plan, line.learning_plan)
        self.assertEqual(member.completion, 0)
        self.env["training.elearning.service"].with_user(learner)._declare(member.id, slide.id)
        self.assertEqual(member.completion, 100)
        self.assertTrue(course.learning_bound_at)
