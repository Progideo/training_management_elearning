"""Native calendar contracts preserve holidays, hours and timezone without HR changes."""

from datetime import datetime
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from .test_activities import LessonCase


@tagged("post_install", "-at_install")
class TestReviewCalendar(LessonCase):
    def test_native_five_day_clock_and_immutable_snapshot(self):
        course = self.course()
        source = self.env["resource.calendar"].create(
            {
                "name": "Fictional review weekdays",
                "company_id": self.env.company.id,
                "calendar_type": "fixed",
                "reference_calendar_id": False,
                "attendance_ids": [
                    Command.create(
                        {
                            "dayofweek": str(day),
                            "hour_from": start,
                            "hour_to": end,
                            "day_period": period,
                        }
                    )
                    for day in range(5)
                    for start, end, period in ((8, 12, "morning"), (13, 17, "afternoon"))
                ],
                "global_leave_ids": [
                    Command.create(
                        {
                            "name": "Fictional Monday holiday",
                            "date_from": datetime(2026, 11, 9),
                            "date_to": datetime(2026, 11, 10),
                            "company_id": self.env.company.id,
                        }
                    )
                ],
            }
        )
        self.env.company.tz = "UTC"
        frozen = source.with_user(self.manager)._learning_snapshot(course)
        self.assertTrue(frozen.learning_review_snapshot)
        receipt = datetime(2026, 11, 6, 16)
        expected = datetime(2026, 11, 16, 16)
        self.assertEqual(frozen._learning_deadline(receipt, 5), expected)
        self.env.company.tz = "Pacific/Auckland"
        source.attendance_ids[:1].write({"hour_from": 7})
        source.global_leave_ids.unlink()
        self.assertEqual(frozen._learning_deadline(receipt, 5), expected)
        for record, values in (
            (frozen, {"active": False}),
            (frozen, {"learning_review_snapshot": False}),
            (frozen.attendance_ids, {"hour_to": 11}),
            (frozen.global_leave_ids, {"name": "changed"}),
            (frozen.learning_review_resource_id, {"tz": "Europe/Paris"}),
        ):
            with self.subTest(model=record._name, values=values), self.assertRaises((AccessError, ValidationError)):
                record.write(values)
        with self.assertRaises(ValidationError):
            frozen.attendance_ids.unlink()
        with self.assertRaises(ValidationError):
            self.env["resource.calendar.leaves"].with_context(default_calendar_id=frozen.id).create(
                {
                    "name": "Forged extra holiday",
                    "date_from": datetime(2026, 12, 1),
                    "date_to": datetime(2026, 12, 2),
                }
            )
        with self.assertRaises(ValidationError):
            self.env["resource.calendar.leaves"].create(
                {
                    "resource_id": frozen.learning_review_resource_id.id,
                    "name": "Forged derived-calendar holiday",
                    "date_from": datetime(2026, 12, 1),
                    "date_to": datetime(2026, 12, 2),
                }
            )
        with self.assertRaises(AccessError):
            self.env["resource.calendar"].create({"name": "Forged contract", "learning_review_snapshot": False})
