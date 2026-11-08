"""Every list and download uses the existing account-bound, time-bound grant."""
from odoo import api, models
from odoo.exceptions import AccessError, MissingError, ValidationError


class ResourceService(models.AbstractModel):
    _name = "training.elearning.resource.service"
    _description = "Private supplementary resource access"

    @api.private
    def _activity(self, membership_id, slide_id):
        result = self.env["training.elearning.service"]._activity(membership_id, slide_id)
        if result[2]["kind"] == "task":
            self.env["training.elearning.practical.service"]._context(membership_id, slide_id)
        return result

    @api.private
    def _context(self, membership_id, slide_id, resource_id):
        member, slide, item = self._activity(membership_id, slide_id)
        expected = next((r for r in item.get("resources", []) if r["id"] == resource_id), None)
        # Narrow sudo only after the ordinary user's grant and exact frozen ID check.
        resource = self.env["slide.slide.resource"].sudo().browse(resource_id).exists() if expected else False
        if not resource or resource.slide_id != slide or resource._resource_snapshot() != expected:
            raise AccessError(self.env._("This private supplementary resource is unavailable."))
        return resource, expected

    @api.private
    def _rows(self, membership_id):
        service = self.env["training.elearning.service"]
        member = service._membership(membership_id, history=True)
        rows = []
        for item in member._learning_plan()["slides"]:
            if not item.get("resources"):
                continue
            try:
                self._activity(membership_id, item["id"])
            except (AccessError, MissingError, ValidationError):
                continue
            # Only frozen scalar metadata is listed. Recheck current bytes/digest on
            # download, avoiding reading every large file just to render the course.
            entries = [dict(entry, url="/my/learning/%s/activities/%s/resources/%s" %
                            (membership_id, item["id"], entry["id"])) for entry in item["resources"]]
            rows.append({"title": item["title"], "entries": entries})
        return rows
