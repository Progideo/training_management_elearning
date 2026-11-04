"""Native sold lines freeze human review conditions independently of later offers."""

from uuid import uuid4
from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged
from odoo.addons.training_elearning.tests.test_human_practical import HumanCase


@tagged("post_install", "-at_install")
class TestPracticalSalePolicy(HumanCase):
    def test_sold_conditions_and_pending_seat_keep_task_version_calendar_and_delays(self):
        course, slide, first, _old_member = self.human()
        commercial = new_test_user(
            self.env,
            login="fictional_practical_commercial",
            groups="training_elearning_sale.group_learning_sales_manager",
        )
        buyer = self.env["res.partner"].create({"name": "Fictional practical purchaser"})
        product = (
            self.env["product.product"]
            .with_user(commercial)
            .create(
                {
                    "name": "Fictional human practical offer",
                    "type": "service",
                    "learning_channel_id": course.id,
                    "learning_review_days": 7,
                    "learning_revision_days": 21,
                }
            )
        )
        order = (
            self.env["sale.order"]
            .with_user(commercial)
            .create(
                {
                    "partner_id": buyer.id,
                    "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1})],
                }
            )
        )
        order.action_confirm()
        line = order.order_line
        frozen = line.learning_plan
        product.write({"learning_review_days": 9, "learning_revision_days": 28})
        with self.assertRaises(ValidationError):
            line.write({"learning_revision_days": 28})
        second = (
            self.env["training.elearning.practical"]
            .with_user(self.manager)
            .browse(first.action_new_version()["res_id"])
        )
        second.write(
            {
                "version_ref": "2",
                "revision_reason": "Fictional reviewed instructions",
                "instructions": "Fictional new instructions",
            }
        )
        second.action_publish()
        self.env["training.elearning.practical.revision"].with_user(self.manager).create(
            {
                "slide_id": slide.id,
                "practical_id": second.id,
                "reason": "Fictional new practical version for future orders",
            }
        ).action_apply()
        line.action_learning_authorize("Fictional checked commercial agreement")
        seat = (
            self.env["training.elearning.sale.allocation"]
            .with_user(commercial)
            .create(
                {
                    "line_id": line.id,
                    "partner_id": self.other.partner_id.id,
                }
            )
        )
        seat.action_learning_activate()
        member = seat.membership_id
        self.assertEqual(member.learning_plan, frozen)
        item = member.learning_plan["slides"][0]
        self.assertEqual(item["task"], first.id)
        self.assertEqual(item["review_days"], 7)
        self.assertEqual(item["revision_days"], 21)
        row = (
            self.env["training.elearning.practical.service"]
            .with_user(self.other)
            ._deposit(
                member.id,
                slide.id,
                [("fictional.txt", b"PRIVATE FICTIONAL SOLD PRACTICAL")],
                str(uuid4()),
            )
        )
        queue = row.review_queue_id
        calendar = self.env["resource.calendar"].browse(item["review_calendar"])
        self.assertEqual(queue.due_at, calendar._learning_deadline(row.received_at, 7))
        self.assertEqual(row.practical_id, first)
        self.assertNotEqual(slide.learning_practical_id, row.practical_id)
