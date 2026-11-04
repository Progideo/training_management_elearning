"""Private editions on native slides; no second course or participant registry."""

from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .revision_scope import lesson_revision, editing_lesson, digest_fields

AUTHOR = "training_elearning.group_elearning_author"
MANAGER = "training_elearning.group_elearning_manager"


class Course(models.Model):
    _inherit = "slide.channel"
    training_course_id = fields.Many2one("training.course", ondelete="restrict", copy=True)
    # Searchable native related field; avoid backfilling unmanaged course audit dates.
    learning_company_id = fields.Many2one(related="training_course_id.company_id")
    learning_editorial_log = fields.Json(readonly=True, copy=False)
    learning_bound_at = fields.Datetime(readonly=True, copy=False)
    learning_state = fields.Selection([("draft", "Draft"), ("published", "Published")], default="draft", copy=False)

    @api.private
    def _learning_staff(self, *, manager=False):
        if not self.env.user.active or not self.env.user.has_group(MANAGER if manager else AUTHOR):
            raise AccessError(self.env._("eLearning coordination permission is required."))
        self.check_access("write")
        if any(course.learning_company_id not in self.env.companies for course in self):
            raise AccessError(self.env._("Use courses in your active companies."))

    @api.private
    def _learning_frozen(self):
        self.lock_for_update()
        return bool(self.filtered("learning_bound_at")) or bool(
            self.env["slide.channel.partner"]
            .sudo()
            .with_context(active_test=False)
            .search_count(
                [("channel_id", "in", self._learning_related_courses().ids), ("learning_started_at", "!=", False)]
            )
        )

    @api.private
    def _learning_bind_graph(self):
        self._learning_lock_graph()
        self._learning_check_graph()
        courses = self._learning_related_courses(ancestors=True).filtered(lambda c: not c.learning_bound_at)
        if courses:
            # A real row update makes the first binding visible to concurrent
            # Repeatable Read editors as well as to later dependency queries.
            super(Course, courses).write({"learning_bound_at": fields.Datetime.now()})  # pylint: disable=super-method-mismatch
        return True

    @api.private
    def _learning_before_revision(self):
        self._learning_lock_graph()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            course_id = vals.get("training_course_id", self.env.context.get("default_training_course_id"))
            if course_id:
                if {"learning_bound_at", "learning_editorial_log"} & vals.keys() or any(
                    "default_" + key in self.env.context for key in ("learning_bound_at", "learning_editorial_log")
                ):
                    raise AccessError(self.env._("Course binding is recorded by the server."))
                self._learning_staff()
                course = self.env["training.course"].browse(course_id)
                course.check_access("read")
                course.lock_for_update()
                if course.company_id not in self.env.companies:
                    raise AccessError(self.env._("Use courses in your active companies."))
                if vals.get("learning_state", self.env.context.get("default_learning_state", "draft")) != "draft":
                    raise AccessError(self.env._("Publish the course through its controlled action."))
                vals.update(
                    # A nonempty command list suppresses native creator auto-enrollment.
                    # Learners are added separately through controlled memberships.
                    channel_partner_ids=[(5, 0, 0)],
                    is_published=False,
                    website_published=False,
                    visibility="members",
                    enroll="invite",
                    enroll_group_ids=[],
                    access_token=False,
                    publish_template_id=False,
                    completed_template_id=False,
                    share_channel_template_id=False,
                    share_slide_template_id=False,
                )
        return super().create(vals_list)

    def write(self, vals):
        managed = self.filtered("training_course_id")
        if {"learning_bound_at", "learning_editorial_log"} & vals.keys():
            raise AccessError(self.env._("Course binding is recorded by the server."))
        if "training_course_id" in vals:
            raise ValidationError(self.env._("Create a new course edition instead of changing its identity."))
        if managed:
            managed._learning_staff(manager="active" in vals)
            if "prerequisite_channel_ids" in vals:
                managed._learning_lock_graph()
            if {"learning_state", "learning_company_id"} & vals.keys():
                raise AccessError(self.env._("Use the controlled course actions."))
            if (
                (
                    vals.get("is_published")
                    or vals.get("website_published")
                    or vals.get("access_token")
                    or vals.get("enroll_group_ids")
                    or vals.get("completed_template_id")
                    or vals.get("publish_template_id")
                    or vals.get("share_channel_template_id")
                    or vals.get("share_slide_template_id")
                )
                or ("visibility" in vals and vals["visibility"] != "members")
                or ("enroll" in vals and vals["enroll"] != "invite")
            ):
                raise ValidationError(self.env._("Keep this course private and on controlled invitation."))
            if {
                "name",
                "description",
                "description_short",
                "description_html",
                "slide_ids",
                "prerequisite_channel_ids",
            } & vals.keys() and managed._learning_frozen():
                raise ValidationError(self.env._("Create a new edition for changed content or obligations."))
        return super().write(vals)

    def action_learning_editorial(self):
        self.ensure_one()
        self._learning_staff()
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.editorial",
            "view_mode": "form",
            "target": "new",
            "context": {"default_course_id": self.id},
        }

    @api.private
    def _learning_apply_editorial(self, values, reason, category):
        self.ensure_one()
        self._learning_staff()
        if not values or set(values) - {"name", "description_html"}:
            raise ValidationError(self.env._("Use a new edition for substantive changes."))
        _check_editorial(self, reason, category)
        with self.env.cr.savepoint():
            self._learning_before_revision()
            before = digest_fields(self, values)
            super(Course, self).write(values)  # pylint: disable=super-method-mismatch
            trace = _editorial_trace(self, before, reason, category)
            super(Course, self).write({"learning_editorial_log": list(self.learning_editorial_log or []) + [trace]})  # pylint: disable=super-method-mismatch
        self.message_post(
            body=Markup("<p>%s</p>")
            % self.env._(
                "Editorial correction (%(category)s): %(reason)s",
                category=_editorial_label(self, category),
                reason=reason.strip(),
            ),
            subtype_xmlid="mail.mt_note",
        )
        return True

    def action_learning_publish(self):
        self._learning_staff()
        self.lock_for_update()
        self._learning_check_contents()
        return super(Course, self).write({"learning_state": "published"})  # pylint: disable=super-method-mismatch

    @api.private
    def _learning_check_contents(self):
        for course in self:
            if not course.training_course_id or not course.active:
                raise ValidationError(self.env._("Check the course identity, active state and prerequisites."))
            course._learning_check_graph()
            contents = course.slide_ids.filtered(lambda slide: not slide.is_category)
            if not contents or any(not slide._learning_supported() for slide in contents):
                raise ValidationError(self.env._("Choose supported published course activities."))

    def _action_add_members(self, target_partners, member_status="joined", raise_on_access=False):
        # Native auto-enrollment must not create a second activation path.
        return super(Course, self.filtered(lambda c: not c.training_course_id))._action_add_members(
            target_partners, member_status=member_status, raise_on_access=raise_on_access
        )

    @api.ondelete(at_uninstall=False)
    def _learning_keep_courses(self):
        if self.filtered("training_course_id")._learning_frozen():
            raise ValidationError(self.env._("Keep course editions with learner history."))


class Slide(models.Model):
    _inherit = "slide.slide"
    learning_editorial_log = fields.Json(readonly=True, copy=False)

    @api.private
    def _learning_supported(self):
        return False

    @api.private
    def _learning_store_version(self, values):
        # Adapters validate version lineage and trace the change before using
        # this private boundary. Ordinary writes keep the edition freeze.
        self.ensure_one()
        self.channel_id._learning_staff()
        self.channel_id._learning_before_revision()
        with lesson_revision(self):
            return super(Slide, self).write(values)  # pylint: disable=super-method-mismatch

    def action_learning_editorial(self):
        self.ensure_one()
        self.channel_id._learning_staff()
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.editorial",
            "view_mode": "form",
            "target": "new",
            "context": {"default_course_id": self.channel_id.id, "default_slide_id": self.id},
        }

    @api.private
    def _learning_apply_editorial(self, values, reason, category):
        self.ensure_one()
        self.channel_id._learning_staff()
        allowed = {
            "article": {"name", "html_content"},
            "document": {"name", "binary_content", "learning_filename"},
            "video": {"name", "video_url"},
        }.get(self.slide_category, set())
        if not values or set(values) - allowed or not self.active:
            raise ValidationError(
                self.env._("Use a new element version or course edition for evaluated or substantive changes.")
            )
        _check_editorial(self, reason, category)
        with self.env.cr.savepoint(), lesson_revision(self):
            self.channel_id._learning_before_revision()
            before = digest_fields(self, values)
            super(Slide, self).write(values)  # pylint: disable=super-method-mismatch
            if not self._learning_supported():
                raise ValidationError(self.env._("Keep a valid, published supported activity."))
            trace = _editorial_trace(self, before, reason, category)
            super(Slide, self).write({"learning_editorial_log": list(self.learning_editorial_log or []) + [trace]})  # pylint: disable=super-method-mismatch
        self.channel_id.message_post(
            body=Markup("<p>%s</p>")
            % self.env._(
                "Editorial correction of %(activity)s (%(category)s): %(reason)s",
                activity=self.name,
                category=_editorial_label(self, category),
                reason=reason.strip(),
            ),
            subtype_xmlid="mail.mt_note",
        )
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "learning_editorial_log" in vals or "default_learning_editorial_log" in self.env.context:
                raise AccessError(self.env._("Editorial history is recorded by the server."))
            course = self.env["slide.channel"].browse(
                vals.get("channel_id") or self.env.context.get("default_channel_id")
            )
            if course.training_course_id:
                course._learning_staff()
                if course._learning_frozen():
                    raise ValidationError(self.env._("Create a new edition for changed content or obligations."))
                vals["is_preview"] = False
        return super().create(vals_list)

    def write(self, vals):
        managed = self.filtered(lambda s: s.channel_id.training_course_id)
        if "learning_editorial_log" in vals:
            raise AccessError(self.env._("Keep the editorial correction history."))
        target = self.env["slide.channel"].browse(vals.get("channel_id"))
        courses = managed.channel_id | target.filtered("training_course_id")
        if courses:
            courses._learning_staff()
            if vals.get("is_preview"):
                raise ValidationError(self.env._("Private course activities cannot be previewed publicly."))
            if set(vals) - {"active"} and courses._learning_frozen() and not editing_lesson(self):
                raise ValidationError(self.env._("Create a new edition for changed content or obligations."))
        return super().write(vals)

    def _post_publication(self):
        return super(Slide, self.filtered(lambda s: not s.channel_id.training_course_id))._post_publication()

    def _action_mark_completed(self):
        if self.sudo().channel_id.filtered("training_course_id"):
            raise AccessError(self.env._("Use the controlled learning completion service."))
        return super()._action_mark_completed()

    def action_mark_uncompleted(self):
        if self.sudo().channel_id.filtered("training_course_id"):
            raise AccessError(self.env._("Keep the server learning evidence."))
        return super().action_mark_uncompleted()

    def _action_set_viewed(self, target_partner, quiz_attempts_inc=False):
        if self.sudo().channel_id.filtered("training_course_id"):
            raise AccessError(self.env._("Use the private learner workspace."))
        return super()._action_set_viewed(target_partner, quiz_attempts_inc=quiz_attempts_inc)

    def _action_set_quiz_done(self, completed=True):
        if self.sudo().channel_id.filtered("training_course_id"):
            raise AccessError(self.env._("Use the controlled learning completion service."))
        return super()._action_set_quiz_done(completed=completed)

    @api.ondelete(at_uninstall=False)
    def _learning_keep_slides(self):
        if self.filtered(lambda s: s.channel_id.training_course_id).channel_id._learning_frozen():
            raise ValidationError(self.env._("Keep course editions with learner history."))


def _check_editorial(record, reason, category):
    if category not in ("typo", "layout", "accessibility", "link") or not (reason or "").strip():
        raise ValidationError(record.env._("Identify the superficial correction and provide its reason."))


def _editorial_trace(record, before, reason, category):
    after = digest_fields(record, before)
    changes = {name: {"before": before[name], "after": after[name]} for name in before if before[name] != after[name]}
    if not changes:
        raise ValidationError(record.env._("No editorial change was provided."))
    return {
        "actor": record.env.uid,
        "at": fields.Datetime.to_string(fields.Datetime.now()),
        "category": category,
        "reason": reason.strip(),
        "changes": changes,
    }


def _editorial_label(record, category):
    labels = record.env["training.elearning.editorial"]._fields["category"]._description_selection(record.env)
    return dict(labels)[category]
