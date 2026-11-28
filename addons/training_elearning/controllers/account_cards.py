from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request


class LearningAccountCards(CustomerPortal):
    def _prepare_portal_counter_values(self, counter):
        if counter == "training_learning_course_count":
            shown = bool(request.env["training.my.courses"]._learning_memberships(limit=5))
            return "res.users", [("id", "=", request.env.uid if shown else 0)], "sudo"
        if counter == "training_learning_path_count":
            shown = bool(request.env["training.elearning.path.service"]._list())
            return "res.users", [("id", "=", request.env.uid if shown else 0)], "sudo"
        return super()._prepare_portal_counter_values(counter)
