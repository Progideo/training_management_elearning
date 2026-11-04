# pylint: disable=super-method-mismatch,context-overridden,method-required-super
"""A curriculum aggregates precise native course editions; it owns no second progress counter."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .course import AUTHOR, MANAGER


class Path(models.Model):
    _name = "training.elearning.path"
    _description = "Autonomous Course Curriculum Edition"
    name = fields.Char(required=True, translate=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        ondelete="restrict",
    )
    active = fields.Boolean(default=True)
    introduction = fields.Text(translate=True)
    line_ids = fields.One2many("training.elearning.path.line", "path_id", copy=True)
    state = fields.Selection(
        [("draft", "Draft"), ("published", "Published")],
        default="draft",
        readonly=True,
        copy=False,
    )
    bound_at = fields.Datetime(readonly=True, copy=False)
    editorial_log = fields.Json(readonly=True, copy=False)

    @api.private
    def _staff(self, *, manager=False):
        user = self.env.user
        if not user.active or not user.has_group(MANAGER if manager else AUTHOR):
            raise AccessError(self.env._("Curriculum coordination permission is required."))
        self.check_access("write")
        if any(path.company_id not in user.company_ids or path.company_id not in self.env.companies for path in self):
            raise AccessError(self.env._("Use curricula in your active operating companies."))

    @api.model_create_multi
    def create(self, vals_list):
        self._staff()
        for values in vals_list:
            if {"bound_at", "editorial_log"} & values.keys() or any(
                "default_" + key in self.env.context for key in ("bound_at", "editorial_log")
            ):
                raise AccessError(self.env._("The server records curriculum binding and editorial changes."))
            if values.get("state", self.env.context.get("default_state", "draft")) != "draft":
                raise AccessError(self.env._("Publish the curriculum through its checked action."))
            company = self.env["res.company"].browse(
                values.get("company_id") or self.env.context.get("default_company_id") or self.env.company.id
            )
            if company not in self.env.user.company_ids or company not in self.env.companies:
                raise AccessError(self.env._("Choose an active operating company."))
        return super().create(vals_list)

    def write(self, values):
        self._staff()
        self.lock_for_update()
        self.invalidate_recordset()
        if {"state", "bound_at", "editorial_log", "company_id"} & values.keys():
            raise AccessError(self.env._("Keep the curriculum identity and use its controlled actions."))
        if self.filtered("bound_at"):
            raise ValidationError(self.env._("Create a new curriculum edition for changed composition or obligations."))
        return super().write(values)

    @api.private
    def _validate(self):
        self.ensure_one()
        path = self.sudo()
        if not path.active or not path.line_ids or not path.line_ids.filtered("required"):
            raise ValidationError(self.env._("Provide an active curriculum and at least one required course."))
        courses = path.line_ids.course_id
        if len(courses) != len(path.line_ids) or any(
            not course.training_course_id
            or not course.active
            or course.learning_state != "published"
            or course.learning_company_id != path.company_id
            for course in courses
        ):
            raise ValidationError(self.env._("Choose distinct published course editions in the curriculum company."))
        courses._learning_lock_graph()
        courses._learning_check_contents()
        optional = path.line_ids.filtered(lambda line: not line.required).course_id
        for course in path.line_ids.filtered("required").course_id:
            if course._learning_related_courses(ancestors=True) & optional:
                raise ValidationError(
                    self.env._("An optional course cannot be an indirect prerequisite of a required course.")
                )
        return courses

    def action_publish(self):
        self._staff()
        self.lock_for_update()
        for path in self:
            path._validate()
        return super(Path, self).write({"state": "published"})

    @api.private
    def _bind(self):
        self.ensure_one()
        self.lock_for_update()
        self.invalidate_recordset()
        if not self.env.user.active or self.company_id not in self.env.user.company_ids or self.state != "published":
            raise AccessError(self.env._("Use a published curriculum in this operating company."))
        courses = self._validate()
        courses._learning_bind_graph()
        if not self.bound_at:
            super(Path, self.sudo()).write({"bound_at": fields.Datetime.now()})
        return True

    @api.private
    def _composition(self):
        self.ensure_one()
        return [
            {
                "course": line.course_id.id,
                "required": line.required,
                "prerequisites": sorted(line.course_id.prerequisite_channel_ids.ids),
            }
            for line in self.sudo().line_ids.sorted("sequence")
        ]

    @api.private
    def _plan(self, included=None):
        self.ensure_one()
        composition = self._composition()
        selected = included if included is not None else [item["course"] for item in composition]
        if not selected or not set(selected) <= {item["course"] for item in composition}:
            raise ValidationError(self.env._("Choose a nonempty explicit subset of this curriculum."))
        return {
            "path": self.id,
            "composition": composition,
            "included": selected,
            "plans": {
                str(item["course"]): self.env["slide.channel"].sudo().browse(item["course"])._learning_plan()
                for item in composition
                if item["course"] in selected
            },
        }

    def action_register(self):
        self.ensure_one()
        self._staff(manager=True)
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.path.activate",
            "view_mode": "form",
            "target": "new",
            "context": {"default_path_id": self.id},
        }

    def action_editorial_name(self, name=None, reason=None):
        self.ensure_one()
        self._staff()
        self.lock_for_update()
        if not (name or "").strip() or not (reason or "").strip():
            raise ValidationError(self.env._("Provide the corrected curriculum title and editorial reason."))
        log = list(self.editorial_log or [])
        log.append(
            {
                "at": fields.Datetime.to_string(fields.Datetime.now()),
                "actor": self.env.uid,
                "before": self.name,
                "after": name.strip(),
                "reason": reason.strip(),
            }
        )
        return super(Path, self).write({"name": name.strip(), "editorial_log": log})

    @api.ondelete(at_uninstall=False)
    def _keep_path(self):
        self._staff()
        self.lock_for_update()
        if self.filtered("bound_at"):
            raise ValidationError(self.env._("Keep curriculum editions with registrations or commercial history."))


class PathLine(models.Model):
    _name = "training.elearning.path.line"
    _description = "Precise Native Course in a Curriculum"
    _order = "sequence, id"
    path_id = fields.Many2one("training.elearning.path", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="path_id.company_id")
    course_id = fields.Many2one("slide.channel", required=True, ondelete="restrict")
    sequence = fields.Integer(default=10)
    required = fields.Boolean(default=True)
    _one_course = models.Constraint("UNIQUE(path_id, course_id)", "This edition is already in the curriculum.")

    @api.private
    def _check_edit(self, values=None):
        values = values or {}
        paths = self.path_id | self.env["training.elearning.path"].browse(values.get("path_id"))
        paths._staff()
        paths.lock_for_update()
        paths.invalidate_recordset()
        if paths.filtered("bound_at"):
            raise ValidationError(self.env._("Keep registered curriculum composition and obligations."))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self.browse()._check_edit({"path_id": values.get("path_id") or self.env.context.get("default_path_id")})
        return super().create(vals_list)

    def write(self, values):
        self._check_edit(values)
        return super().write(values)

    @api.constrains("path_id", "course_id")
    def _check_company(self):
        if any(
            not line.course_id.training_course_id or line.course_id.learning_company_id != line.path_id.company_id
            for line in self
        ):
            raise ValidationError(self.env._("Choose a managed native course in this curriculum company."))

    @api.ondelete(at_uninstall=False)
    def _keep_line(self):
        self._check_edit()


class Registration(models.Model):
    _name = "training.elearning.path.registration"
    _description = "Learner Curriculum Aggregation Context"
    _rec_name = "path_id"
    path_id = fields.Many2one("training.elearning.path", required=True, readonly=True, ondelete="restrict")
    company_id = fields.Many2one(related="path_id.company_id")
    partner_id = fields.Many2one("res.partner", required=True, readonly=True, ondelete="restrict")
    user_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    registered_at = fields.Datetime(required=True, readonly=True)
    composition = fields.Json(required=True, readonly=True)
    activation_ids = fields.One2many("training.elearning.path.activation", "registration_id", readonly=True)
    _one_registration = models.Constraint(
        "UNIQUE(path_id, partner_id)",
        "This learner already has this curriculum context.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Register through an explicitly authorized curriculum activation."))

    def write(self, values):
        raise AccessError(self.env._("Keep the learner identity and frozen curriculum composition."))

    @api.ondelete(at_uninstall=False)
    def _keep_registration(self):
        raise AccessError(self.env._("Keep curriculum history."))

    @api.private
    def _ensure_registration(self, path, partner, composition):
        path._staff(manager=True)
        path._bind()
        if composition != path._composition():
            raise ValidationError(self.env._("Keep the precise published curriculum composition."))
        partner.check_access("read")
        if partner.company_id and partner.company_id != path.company_id:
            raise AccessError(self.env._("Choose a beneficiary in this operating company."))
        users = partner.sudo().with_context(active_test=False).user_ids
        if len(users) != 1 or not users.active or users._is_public() or path.company_id not in users.company_ids:
            raise ValidationError(self.env._("Prepare the beneficiary unique active native Odoo account."))
        existing = self.sudo().search([("path_id", "=", path.id), ("partner_id", "=", partner.id)], limit=1)
        if existing:
            if existing.user_id != users or existing.composition != composition:
                raise ValidationError(self.env._("Keep the learner identity and registered curriculum edition."))
            return existing
        return super(Registration, self.sudo().with_context({})).create(
            {
                "path_id": path.id,
                "partner_id": partner.id,
                "user_id": users.id,
                "composition": composition,
                "registered_at": fields.Datetime.now(),
            }
        )

    @api.private
    def _member(self, course_id):
        self.ensure_one()
        return (
            self.env["slide.channel.partner"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("channel_id", "=", course_id),
                    ("partner_id", "=", self.sudo().partner_id.id),
                    ("learning_user_id", "=", self.sudo().user_id.id),
                ],
                limit=1,
            )
        )

    @api.private
    def _summary(self):
        self.ensure_one()
        rows = []
        for item in self.sudo().composition:
            course = self.env["slide.channel"].sudo().browse(item["course"]).exists()
            member = self._member(item["course"])
            complete = bool(member.learning_started_at and member._learning_progress()["complete"])
            rows.append(
                {
                    **item,
                    "title": course.name,
                    "prerequisite_titles": self.env["slide.channel"]
                    .sudo()
                    .browse(item["prerequisites"])
                    .mapped("name"),
                    "complete": complete,
                    "completed_at": member.completion_date if complete else False,
                    "member": member.id if member.learning_started_at else False,
                }
            )
        required = [row for row in rows if row["required"]]
        completed = [row for row in required if row["complete"]]
        achieved = bool(required and len(completed) == len(required))
        dates = [row["completed_at"] for row in completed if row["completed_at"]]
        return {
            "rows": rows,
            "required": len(required),
            "satisfied": len(completed),
            "percentage": round(100 * len(completed) / len(required)) if required else 0,
            "complete": achieved,
            "completed_at": max([self.registered_at, *dates]) if achieved else False,
        }
