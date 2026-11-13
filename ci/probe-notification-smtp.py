# ruff: noqa: F821 -- native Odoo shell supplies env.
"""Actual native SMTP into a disposable sink; fictional recipients only, no relay."""

import json
from email import message_from_string
from datetime import timedelta
from urllib.request import urlopen
from uuid import uuid4
from odoo import fields, Command
from odoo.tests import new_test_user
from odoo.tools import config

assert env.cr.dbname == "tm_suite_test"
assert not config["test_enable"], "Use a real native transport, outside the mocked Odoo test runner"


def received():
    with urlopen("http://learning-smtp:8025/messages", timeout=10) as response:
        return json.load(response)


def bodies(receipt):
    result = []
    for row in receipt["messages"]:
        message = message_from_string(row["data"])
        result.append(
            "\n".join(
                part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                for part in message.walk()
                if part.get_content_maintype() == "text"
            )
        )
    return result


assert received()["count"] == 0
coordinator = new_test_user(
    env,
    login="fictional_confined_notification_coordinator",
    groups="training_elearning_sale.group_learning_sales_manager,training_elearning.group_elearning_pedagogy_manager",
    email="fictional.coordination@example.invalid",
)
buyer = env["res.partner"].create({"name": "Fictional confined purchaser"})
catalog = env["training.course"].create({"name": "Fictional confined invitation catalogue"})
course = (
    env["slide.channel"]
    .with_user(coordinator)
    .create({"name": "Fictional confined invitation edition", "training_course_id": catalog.id})
)
env["slide.slide"].with_user(coordinator).create(
    {
        "name": "Fictional confined article",
        "channel_id": course.id,
        "slide_category": "article",
        "html_content": "<p>PRIVATE CONFINED ARTICLE</p>",
        "is_published": True,
    }
)
course.action_learning_publish()
product = (
    env["product.product"]
    .with_user(coordinator)
    .create({"name": "Fictional confined native offer", "type": "service", "learning_channel_id": course.id})
)
order = (
    env["sale.order"]
    .with_user(coordinator)
    .create({"partner_id": buyer.id, "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 3})]})
)
order.action_confirm()
order.order_line.action_learning_authorize("Fictional confined notification qualification")
server = env["ir.mail_server"].create(
    {
        "name": "Fictional isolated SMTP sink",
        "smtp_host": "learning-smtp",
        "smtp_port": 2525,
        "smtp_encryption": "none",
        "sequence": 1,
    }
)


def invitation(email):
    partner = env["res.partner"].create({"name": "Fictional confined beneficiary", "email": email})
    seat = (
        env["training.elearning.sale.allocation"]
        .with_user(coordinator)
        .create({"line_id": order.order_line.id, "partner_id": partner.id})
    )
    seat.action_learning_activate()
    notice = (
        env["training.elearning.reminder"].sudo().search([("allocation_id", "=", seat.id), ("kind", "=", "invitation")])
    )
    assert notice.state == "queued" and notice.mail_id.state == "outgoing"
    notice.mail_id.write({"mail_server_id": server.id})
    return seat, notice


seat, invite = invitation("fictional.invited@example.invalid")
invite.mail_id.send(raise_exception=True)
assert invite.mail_id.state == "sent" and invite.state == "sent"
receipt = received()
assert receipt["count"] == 1
assert "fictional.invited@example.invalid" in str(receipt["messages"][0]["to"])
assert "/web/signup" in bodies(receipt)[0]
assert "PRIVATE CONFINED ARTICLE" not in bodies(receipt)[0]
print("J20_NATIVE_PORTAL_INVITATION_DELIVERED_TO_CONFINED_SMTP")

blocked_seat, blocked = invitation("fictional.blocked@example.invalid")
blocked_seat.membership_id.learning_user_id.with_env(env).active = False
blocked.mail_id.send(raise_exception=True)
assert blocked.mail_id.state == "cancel" and received()["count"] == 1
print("J20_REVOKED_NATIVE_INVITATION_CANCELLED_BEFORE_SMTP")

failed_seat, failed = invitation("reject.learner@example.invalid")
failed.mail_id.send(raise_exception=False)
assert failed.mail_id.state == "exception" and failed.state == "exception" and failed.incident_activity_id
assert failed_seat.activated_at and failed_seat.membership_id.learning_state == "active"
assert received()["count"] == 1
failed_seat.partner_id.email = "fictional.recovered@example.invalid"
failed.with_user(coordinator).action_retry()
failed.mail_id.send(raise_exception=True)
assert failed.mail_id.state == "sent" and failed.state == "sent" and received()["count"] == 2
print("J20_NATIVE_SMTP_REJECTION_AND_SAME_EVENT_RETRY_PRESERVE_ACCESS")

learner = seat.membership_id.learning_user_id
human_course = (
    env["slide.channel"]
    .with_user(coordinator)
    .create(
        {
            "name": "Fictional confined human correction",
            "training_course_id": catalog.id,
            "learning_reviewer_id": coordinator.id,
        }
    )
)
task = (
    env["training.elearning.practical"]
    .with_user(coordinator)
    .create(
        {
            "name": "Fictional confined practical",
            "training_course_id": catalog.id,
            "criterion": "human",
            "instructions": "PRIVATE CONFINED INSTRUCTIONS",
            "rubric_ids": [Command.create({"description": "PRIVATE CONFINED CRITERION"})],
        }
    )
)
task.action_publish()
slide = (
    env["slide.slide"]
    .with_user(coordinator)
    .create({"channel_id": human_course.id, "learning_practical_id": task.id, "is_published": True})
)
human_course.action_learning_publish()
member = (
    env["slide.channel.partner"]
    .with_user(coordinator)
    .create({"channel_id": human_course.id, "partner_id": learner.partner_id.id})
)
member.action_learning_activate(fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional confined human grant")
submission = (
    env["training.elearning.practical.service"]
    .with_user(learner)
    ._deposit(member.id, slide.id, [("fictional.txt", b"PRIVATE CONFINED LEARNER WORK")], str(uuid4()))
)
queue = submission.review_queue_id
review = queue.with_user(coordinator)._publish(
    submission.id, "revision", {str(criterion.id): False for criterion in task.rubric_ids}, "PRIVATE CONFINED FEEDBACK"
)
feedback = review.delivery_notice_id
assert not queue.revision_until
feedback.mail_id.write({"mail_server_id": server.id})
feedback.mail_id.send(raise_exception=True)
assert feedback.state == "sent" and not feedback.failed and feedback.sent_at
assert queue.state == "revision" and queue.revision_until == feedback.sent_at + timedelta(days=14)
receipt = received()
assert receipt["count"] == 3
assert all("PRIVATE CONFINED" not in body for body in bodies(receipt))
assert all("Content-Disposition: attachment" not in message["data"] for message in receipt["messages"])
assert (
    env["training.elearning.reminder"]
    .sudo()
    .search_count([("queue_id", "=", queue.id), ("kind", "=", "revision_end"), ("state", "=", "pending")])
    == 1
)
print("J20_NATIVE_FEEDBACK_SMTP_OPENS_FULL_REVISION_CLOCK_WITHOUT_PEDAGOGICAL_ATTACHMENT")
# No real recipient, server, token or queued message survives this disposable qualification transaction.
env.cr.rollback()
