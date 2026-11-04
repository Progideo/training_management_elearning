"""Explicit public general offers, independent of private native course publication."""

from odoo import api, fields, models


class Course(models.Model):
    _inherit = "slide.channel"

    learning_public_catalogue = fields.Boolean(string="Présenter l’offre générale au catalogue", copy=False)
    learning_public_conditions = fields.Text(string="Conditions commerciales publiques", translate=True)


class Catalogue(models.Model):
    _inherit = "training.course"

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
        return offers + [
            {
                "course_id": course.training_course_id.id,
                "title": course.name,
                "mode": "autonomous",
                "kind": self.env._("Autonome"),
                "conditions": course.learning_public_conditions or "",
                "url": "/contactus",
                "action": self.env._("Demander une offre autonome"),
            }
            for course in courses
        ]
