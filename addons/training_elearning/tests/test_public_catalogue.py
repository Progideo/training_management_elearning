"""Publishing a general offer cannot publish a native private course or its contents."""

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from .test_activities import LessonCase


@tagged("post_install", "-at_install")
class TestPublicAutonomousOffers(LessonCase, HttpCase):
    def test_explicit_general_offer_keeps_native_contents_private(self):
        self.catalog.write(
            {"presentation": "FICTIONAL GENERAL PRESENTATION", "general_objectives": "FICTIONAL GENERAL OBJECTIVES"}
        )
        course = self.course(
            name="Fictional public autonomous offer", description_html="<p>SECRET NATIVE DESCRIPTION</p>"
        )
        article = self.article(course)
        course.action_learning_publish()
        self.authenticate(None, None)
        page_url = "/formations/catalogue/%s" % self.catalog.id
        self.assertEqual(self.url_open(page_url).status_code, 404)
        self.assertNotIn(course.name, self.url_open("/formations").text)
        course.write({"learning_public_catalogue": True, "learning_public_conditions": "FICTIONAL PUBLIC TERMS"})
        response = self.url_open(page_url)
        self.assertEqual(response.status_code, 200)
        for value in (
            "FICTIONAL GENERAL PRESENTATION",
            "FICTIONAL GENERAL OBJECTIVES",
            "FICTIONAL PUBLIC TERMS",
            course.name,
        ):
            self.assertIn(value, response.text)
        for value in ("SECRET NATIVE DESCRIPTION", article.name, "PRIVATE LESSON TEXT"):
            self.assertNotIn(value, response.text)
        self.assertEqual(self.url_open("/contactus").status_code, 200)
        self.assertIn(course.name, self.url_open("/formations?mode=autonomous").text)
        self.assertNotIn(course.name, self.url_open("/formations?search=SECRET%20NATIVE").text)
        self.assertFalse(course.is_published or article.is_preview)
        for url in (course.website_url, article.website_url):
            self.assertIn(self.url_open(url).status_code, (403, 404))
        with self.assertRaises(AccessError):
            course.with_user(self.env.ref("base.public_user")).read(["slide_ids"])
        self.member(course)
        course.write({"learning_public_catalogue": False})
        self.assertEqual(self.url_open(page_url).status_code, 404)
        # Removing a public listing grants or revokes no pedagogical right.
        service = self.env["training.elearning.service"].with_user(self.learner)
        member = (
            self.env["slide.channel.partner"]
            .sudo()
            .search([("channel_id", "=", course.id), ("partner_id", "=", self.learner.partner_id.id)])
        )
        service._activity(member.id, article.id)

    def test_coexisting_modes_keep_one_public_identity_without_access_grants(self):
        if "training.program.version" not in self.env:
            self.skipTest("The two-mode public catalogue is qualified in coexistence")
        from odoo.tests import new_test_user

        coordinator = new_test_user(
            self.env, login="fictional_public_tm_coordinator", groups="training_management.group_training_coordinator"
        )
        self.catalog.category_id = self.env["training.category"].create({"name": "Fictional public shared category"})
        contact = self.env["res.partner"].create({"name": "Fictional public contact"})
        program = (
            self.env["training.program.version"]
            .with_user(coordinator)
            .create(
                {
                    "course_id": self.catalog.id,
                    "version": "Public-1",
                    "title": "Fictional supervised offer",
                    "objectives": "Fictional general objectives",
                    "target_audience": "Beginners",
                    "prerequisites": "General prerequisites",
                    "content": "SECRET SUPERVISED PROGRAMME",
                    "duration_hours": 7,
                    "delivery_mode": "remote",
                    "language_id": self.env.ref("base.lang_en").id,
                    "teaching_methods": "Exercises",
                    "evaluation_criteria": "Review",
                    "access_conditions": "On quotation",
                    "accessibility_contact_id": contact.id,
                    "accessibility_information": "Contact us",
                    "public_catalogue": True,
                }
            )
        )
        program.action_validate()
        program.action_publish()
        course = self.course(
            learning_public_catalogue=True, learning_public_conditions="Fictional autonomous conditions"
        )
        self.article(course)
        course.action_learning_publish()
        rows = self.env["training.course"]._catalogue_rows(self.env.company)
        shared = [row for row in rows if row["id"] == self.catalog.id]
        self.assertEqual(len(shared), 1)
        self.assertEqual(len(shared[0]["offers"]), 2)
        self.assertEqual({offer["mode"] for offer in shared[0]["offers"]}, {"remote", "autonomous"})
        self.authenticate(None, None)
        response = self.url_open("/formations/catalogue/%s" % self.catalog.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn(program.title, response.text)
        self.assertIn(course.name, response.text)
        self.assertNotIn(program.content, response.text)
        self.assertNotIn("PRIVATE LESSON TEXT", response.text)
        self.assertFalse(self.env["slide.channel.partner"].sudo().search_count([("channel_id", "=", course.id)]))
        self.assertFalse(self.env["training.enrollment"].sudo().search_count([("program_id", "=", program.id)]))
