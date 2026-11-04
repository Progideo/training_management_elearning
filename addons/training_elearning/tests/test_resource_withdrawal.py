"""A library retirement follows frozen versions and leaves acquisitions intact."""

from odoo.exceptions import AccessError
from odoo.tests import tagged
from .test_interactive import InteractiveCase


@tagged("post_install", "-at_install")
class TestSharedResourceWithdrawal(InteractiveCase):
    def test_retirement_notifies_only_frozen_old_cohort_without_replacing_or_invalidating(self):
        course, slide, old, member = self.interactive()
        attempt = self.start(member, slide)
        attempt._save(
            "retained-pass",
            1,
            {
                "state": {"page": "Fictional retained position"},
                "result": {"score": 100, "maximum": 100, "completed": True},
            },
        )
        evidence = self.env["slide.slide.partner"].search(
            [("slide_id", "=", slide.id), ("partner_id", "=", self.learner.partner_id.id)]
        )
        first = evidence.learning_completed_at
        events = self.env["training.elearning.interactive.event"].sudo().search([("attempt_id", "=", attempt.id)]).ids
        newer = self.version(resource=old.resource_id, number="2")
        self.env["training.elearning.interactive.revision"].with_user(self.manager).create(
            {
                "slide_id": slide.id,
                "version_id": newer.id,
                "threshold": 70,
                "reason": "Fictional version change for future cohorts",
            }
        ).action_apply()
        later = self.member(course, self.other)
        self.assertEqual(member.learning_plan["slides"][0]["version"], old.id)
        self.assertEqual(later.learning_plan["slides"][0]["version"], newer.id)
        old.with_user(self.librarian)._withdraw("Fictional motivated library retirement")
        notices = (
            self.env["training.elearning.reminder"]
            .sudo()
            .search([("kind", "=", "resource_withdrawal"), ("interactive_version_id", "=", old.id)])
        )
        self.assertEqual(notices.membership_id, member)
        self.assertEqual(notices.state, "queued")
        self.assertEqual(notices.mail_id.recipient_ids, self.learner.partner_id)
        self.assertTrue(notices.mail_id._learning_delivery_allowed())
        self.assertEqual(member.completion, 100)
        self.assertEqual(evidence.learning_completed_at, first)
        self.assertEqual(
            self.env["training.elearning.interactive.event"].sudo().search([("attempt_id", "=", attempt.id)]).ids,
            events,
        )
        self.assertEqual(slide.learning_interactive_version_id, newer)
        self.assertEqual(member.learning_plan["slides"][0]["version"], old.id)
        self.assertTrue(course.activity_ids.filtered(lambda activity: activity.user_id == self.manager))
        self.assertNotIn("Fictional motivated library retirement", str(notices.mail_id.body_html))
        with self.assertRaises(AccessError):
            attempt._save(
                "retired-result", 2, {"state": {}, "result": {"score": 100, "maximum": 100, "completed": True}}
            )
        service = self.env["training.elearning.service"]
        with self.assertRaises(AccessError):
            service.with_user(self.learner)._activity(member.id, slide.id)
        self.assertTrue(service.with_user(self.other)._activity(later.id, slide.id))
        with self.assertRaises(AccessError):
            notices.with_user(self.librarian).read(["membership_id"])

    def test_unacquired_required_retirement_stays_unavailable_without_failure_or_extension(self):
        _course, slide, version, member = self.interactive()
        end = member.learning_ends_at
        version.with_user(self.librarian)._withdraw("Fictional unavailable required resource")
        self.assertEqual(member.completion, 0)
        self.assertEqual(member.learning_ends_at, end)
        item = member._learning_plan()["slides"][0]
        status = self.env["training.elearning.service"]._item_status(member, item)
        self.assertFalse(status["complete"])
        self.assertTrue(status["unavailable"])
        self.assertEqual(status["state"], "unavailable")
        notice = (
            self.env["training.elearning.reminder"]
            .sudo()
            .search([("membership_id", "=", member.id), ("kind", "=", "resource_withdrawal")])
        )
        self.assertEqual(notice.interactive_version_id, version)
        with self.assertRaises(AccessError):
            self.env["ir.binary"]._get_stream_from(version.file_ids[0], "data")
        self.learner.with_env(self.env).active = False
        self.assertFalse(notice.mail_id._learning_delivery_allowed())
