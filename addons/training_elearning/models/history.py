"""Owned history stays navigable after expiry without reopening pedagogical content."""

from odoo import api, models


class Service(models.AbstractModel):
    _inherit = "training.elearning.service"

    @api.private
    def _history_entries(self, member, item):
        if item["kind"] == "task":
            submissions = (
                self.env["training.elearning.submission"]
                .sudo()
                .search(
                    [
                        ("membership_id", "=", member.id),
                        ("slide_id", "=", item["id"]),
                    ],
                    order="received_at desc,id desc",
                )
            )
            return [
                {
                    "label": "Rendu personnel et retour individuel",
                    "date": row.received_at,
                    "url": "/my/learning-submissions/%s" % row.id,
                    "themes": [],
                }
                for row in submissions
            ]
        if item["kind"] == "interactive":
            return [
                {
                    "label": "Mes scores et dates de tentatives formatives",
                    "date": False,
                    "url": self._activity_url(member, item),
                    "themes": [],
                }
            ]
        return []

    @api.private
    def _history(self, membership_id):
        member = self._membership(membership_id, history=True)
        rows = []
        for item in member._learning_plan()["slides"]:
            evidence = (
                self.env["slide.slide.partner"]
                .sudo()
                .search(
                    [
                        ("slide_id", "=", item["id"]),
                        ("partner_id", "=", member.partner_id.id),
                    ],
                    limit=1,
                )
            )
            event = self.env["training.elearning.acquisition.invalidation"]._latest(member, item["id"])
            rows.append(
                {
                    "title": item["title"],
                    "required": item["required"],
                    "complete": self._item_status(member, item)["complete"],
                    "acquired_at": evidence.learning_completed_at,
                    "invalidated_at": event.invalidated_at if event else False,
                    "restored_at": event.restored_at if event else False,
                    "entries": self._history_entries(member, item),
                }
            )
        return {"id": member.id, "title": member.channel_id.name, "rows": rows}

    @api.private
    def _period_result_evidence(self, member, item, cutoff):
        """Optional typed result evidence; no purchase or commercial dependency."""
        return False
