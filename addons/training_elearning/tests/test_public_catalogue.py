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
        # No autonomy without a public price (TM #186, 21 November 2026): the price comes from
        # the application that sells the offer, absent here, so the offer stays unlisted.
        response = self.url_open(page_url)
        self.assertEqual(response.status_code, 404)
        for value in ("SECRET NATIVE DESCRIPTION", article.name, "PRIVATE LESSON TEXT", "FICTIONAL PUBLIC TERMS"):
            self.assertNotIn(value, response.text)
        self.assertEqual(self.url_open("/contactus").status_code, 200)
        self.assertNotIn(course.name, self.url_open("/formations?mode=autonomous").text)
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
        editor = new_test_user(
            self.env, login="fictional_public_catalogue_editor", groups="base.group_user,training_catalog.group_catalog_editor"
        )
        tag_group = self.env["slide.channel.tag.group"].create({"name": "Fictional topic group"})
        public_tag, internal_tag = self.env["slide.channel.tag"].create([
            {"name": "FICTIONAL SHARED TOPIC", "group_id": tag_group.id, "color": 7},
            {"name": "SECRET INTERNAL TAG", "group_id": tag_group.id, "color": 0},
        ])
        self.assertEqual(public_tag.with_user(editor).name, "FICTIONAL SHARED TOPIC")
        with self.assertRaises(ValueError), self.env.cr.savepoint():
            self.catalog.with_user(editor).write({"public_tag_ids": [(4, internal_tag.id)]})
        self.catalog.with_user(editor).write(
            {
                "presentation": "FICTIONAL SHARED PRESENTATION",
                "public_tag_ids": [(4, public_tag.id)],
            }
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
                    "delivery_mode": "onsite",
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
        # No autonomy without a public price (TM #186): only the trainer-led offer is presented.
        self.assertEqual({offer["mode"] for offer in shared[0]["offers"]}, {"onsite"})
        self.authenticate(None, None)
        page_url = "/formations/catalogue/%s" % self.catalog.id
        response = self.url_open(page_url)
        self.assertEqual(response.status_code, 200)
        # The trainer-led version is presented through its public conditions; the unpriced
        # autonomous course is not presented.
        self.assertIn(program.access_conditions, response.text)
        self.assertNotIn("Fictional autonomous conditions", response.text)
        self.assertNotIn(program.content, response.text)
        self.assertNotIn("PRIVATE LESSON TEXT", response.text)
        for url in (
            "/formations?mode=onsite",
            page_url,
            "/formations/%s" % program.id,
        ):
            html = self.url_open(url).text
            self.assertIn("FICTIONAL SHARED PRESENTATION", html)
            self.assertIn("FICTIONAL SHARED TOPIC", html)
            self.assertIn("o_wslides_channel_tag o_color_7", html)
            self.assertNotIn("SECRET INTERNAL TAG", html)
        public_tag.write({"name": "FICTIONAL UPDATED TOPIC", "color": 3})
        html = self.url_open(page_url).text
        self.assertIn("FICTIONAL UPDATED TOPIC", html)
        self.assertIn("o_wslides_channel_tag o_color_3", html)
        self.assertIn(self.catalog.name, self.url_open("/formations?search=FICTIONAL%20UPDATED%20TOPIC").text)
        public_tag.color = 0
        self.assertNotIn("FICTIONAL UPDATED TOPIC", self.url_open(page_url).text)
        self.assertFalse(self.env["slide.channel.partner"].sudo().search_count([("channel_id", "=", course.id)]))
        self.assertFalse(self.env["training.enrollment"].sudo().search_count([("program_id", "=", program.id)]))

    def test_course_review_requires_actual_completion_for_the_signed_in_learner(self):
        self.catalog.public_catalogue = True
        edition = self.course()
        first = self.article(edition)
        second = self.article(edition, name="Fictional second mandatory article")
        edition.action_learning_publish()
        member = self.member(edition)
        service = self.env["training.elearning.service"].with_user(self.learner)
        self.assertFalse(self.catalog._course_review_status(self.learner))
        service._declare(member.id, first.id)
        self.assertFalse(self.catalog._course_review_status(self.learner))
        service._declare(member.id, second.id)
        self.assertEqual(self.catalog._course_review_status(self.learner), "eligible")
        self.assertFalse(self.catalog._course_review_status(self.other))
        self.catalog._submit_course_review(self.learner, "5", "Fictional autonomous review", "1")
        self.assertEqual(self.catalog._course_review_status(self.learner), "pending")
        self.assertFalse(self.catalog._public_reviews())

    def test_autonomous_catalogue_facts_are_scalars_only(self):
        course = self.course(name="Fictional autonomous facts", description_html="<p>SECRET NATIVE DESCRIPTION</p>")
        article = self.article(course)
        course.action_learning_publish()
        company = course.learning_company_id
        facts = self.catalog.sudo()._catalogue_facts(company)[self.catalog.id]
        self.assertIsNone(facts["autonomous"])
        course.write({"learning_public_catalogue": True})
        autonomous = self.catalog.sudo()._catalogue_facts(company)[self.catalog.id]["autonomous"]
        self.assertEqual(autonomous["modules"], course.total_slides)
        self.assertEqual(autonomous["hours"], course.total_time)
        self.assertEqual(set(autonomous), {"hours", "modules", "access_months", "price"})
        self.assertNotIn(article.name, str(autonomous))
