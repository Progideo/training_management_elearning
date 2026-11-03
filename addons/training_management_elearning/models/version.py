"""Legacy TM reader adapter; package storage is owned by training_interactive."""
from odoo import models

AUTHOR = "training_interactive.group_interactive_author"
COORDINATOR = "training_management.group_training_coordinator"


class Version(models.Model):
    _inherit = "training.elearning.version"

    def action_preview(self):
        self.ensure_one()
        self.check_access("read")
        return {"type": "ir.actions.act_url", "url": "/training/interactive/preview/%s" % self.id, "target": "new"}
