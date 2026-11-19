"""Explicit public general offers, independent of private native course publication."""

from odoo import api, fields, models

PUBLIC_TAG_COLORS = tuple(range(1, 12))


class Course(models.Model):
    _inherit = "slide.channel"

    learning_public_catalogue = fields.Boolean(string="Présenter l’offre générale au catalogue", copy=False)
    learning_public_conditions = fields.Text(string="Conditions commerciales publiques", translate=True)


    @api.private
    def _catalogue_shop_offers(self, company):
        return {}

class Catalogue(models.Model):
    _inherit = "training.course"

    public_tag_ids = fields.Many2many(
        "slide.channel.tag",
        relation="training_course_public_tag_rel",
        string="Étiquettes publiques",
        domain=[("color", "in", list(PUBLIC_TAG_COLORS))],
    )

    @api.private
    def _catalogue_tags(self):
        values = super()._catalogue_tags()
        for course in self:
            native = course.public_tag_ids.filtered(lambda tag: tag.color in PUBLIC_TAG_COLORS)
            native = native.sorted(lambda tag: (tag.group_sequence, tag.sequence, tag.id))
            labels = {tag.name for tag in native}
            values[course.id] = [tag for tag in values[course.id] if tag["label"] not in labels] + [
                {"label": tag.name, "color": tag.color} for tag in native
            ]
        return values

    @api.private
    def _catalogue_offers(self, company):
        offers = super()._catalogue_offers(company)
        # This flag grants only the general title and manually approved terms.
        # Native descriptions, slide titles, prerequisites, files and results
        # never enter the public projection. Website/native slide grants stay off.
        courses = (
            self.env["slide.channel"]
            .sudo()
            .search(
                [
                    ("training_course_id", "!=", False),
                    ("learning_company_id", "=", company.id),
                    ("learning_state", "=", "published"),
                    ("active", "=", True),
                    ("learning_public_catalogue", "=", True),
                ]
            )
        )
        shop_offers = courses._catalogue_shop_offers(company)
        for course in courses:
            presentation = {
                "course_id": course.training_course_id.id,
                "title": course.name,
                "mode": "autonomous",
                "kind": self.env._("Autonome"),
                "conditions": course.learning_public_conditions or "",
            }
            products = shop_offers.get(course.id)
            if products:
                offers.extend(
                    {
                        **presentation,
                        "title": product["name"] if len(products) > 1 else course.name,
                        "url": product["url"],
                        "action": self.env._("S’inscrire en eLearning"),
                    }
                    for product in products
                )
            else:
                offers.append(
                    {
                        **presentation,
                        "url": "/contactus",
                        "action": self.env._("Demander une offre autonome"),
                    }
                )
        return offers

    @api.private
    def _catalogue_public_channels(self, company):
        """Explicitly presented, published autonomous courses of this operator."""
        return (
            self.env["slide.channel"]
            .sudo()
            .search(
                [
                    ("training_course_id", "in", self.ids),
                    ("learning_company_id", "=", company.id),
                    ("learning_state", "=", "published"),
                    ("active", "=", True),
                    ("learning_public_catalogue", "=", True),
                ],
                order="id",
            )
        )

    @api.private
    def _catalogue_facts(self, company):
        # The shared catalogue hook exists from Training Management lot 1; older
        # versions never call it, so this projection stays optional.
        parent = getattr(super(), "_catalogue_facts", None)
        facts = parent(company) if parent else {course.id: {} for course in self}
        channels = self._catalogue_public_channels(company)
        for course in self:
            channel = channels.filtered(lambda c, t=course: c.training_course_id == t)[:1]
            # Scalars only: no native description, slide title or file is projected.
            facts[course.id]["autonomous"] = (
                {
                    "hours": channel.total_time,
                    "modules": channel.total_slides,
                    "access_months": None,
                    "price": None,
                }
                if channel
                else None
            )
        return facts

    @api.private
    def _has_course_review_participation(self, user):
        self.ensure_one()
        if super()._has_course_review_participation(user):
            return True
        memberships = self.env["slide.channel.partner"].sudo().search(
            [
                ("channel_id.training_course_id", "=", self.id),
                ("channel_id.learning_company_id", "=", self.company_id.id),
                ("learning_user_id", "=", user.id),
                ("partner_id", "=", user.partner_id.id),
                ("learning_started_at", "!=", False),
                ("learning_state", "=", "active"),
                ("member_status", "=", "completed"),
            ]
        )
        for member in memberships:
            progress = member._learning_progress()
            if progress["required"] and progress["complete"]:
                return True
        return False
