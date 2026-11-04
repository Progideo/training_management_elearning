"""Shared versions on native lessons; native membership is the sole learner context."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

OBLIGATIONS = [("optional", "Optional"), ("complete", "Required to Complete"), ("pass", "Required to Pass")]


class Slide(models.Model):
    _inherit = "slide.slide"
    learning_exam_obligation = fields.Selection(OBLIGATIONS)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            course = self.env["slide.channel"].browse(
                vals.get("channel_id") or self.env.context.get("default_channel_id")
            )
            if course.training_course_id and vals.get("survey_id"):
                vals.setdefault("name", self.env["survey.survey"].browse(vals["survey_id"]).title)
                vals.update(slide_category="certification", is_preview=False)
                vals.setdefault("learning_exam_obligation", "pass")
        return super().create(vals_list)

    @api.constrains("survey_id", "channel_id", "learning_exam_obligation", "is_published", "slide_category")
    def _learning_check_exam(self):
        for slide in self.filtered(
            lambda s: (
                s.channel_id.training_course_id
                and not s.is_category
                and (s.survey_id or s.slide_category == "certification")
            )
        ):
            if (
                not slide.survey_id
                or slide.survey_id.training_course_id != slide.channel_id.training_course_id
                or slide.survey_id.mock_company_id != slide.channel_id.learning_company_id
                or slide.survey_id.training_state != "published"
                or not slide.learning_exam_obligation
                or slide.slide_category != "certification"
            ):
                raise ValidationError(self.env._("Select a published shared exam from this course and company."))

    @api.private
    def _learning_supported(self):
        self.ensure_one()
        if self.slide_category == "certification" or self.survey_id:
            # Classification only: coordination does not acquire question access.
            return bool(
                self.sudo().survey_id.training_course_id
                and self.is_published
                and self.active
                and self.learning_exam_obligation
            )
        return super()._learning_supported()

    @api.private
    def _learning_plan_item(self):
        if not self.survey_id:
            return super()._learning_plan_item()
        return {
            "id": self.id,
            "kind": "exam",
            "required": self.learning_exam_obligation != "optional",
            "exam": self.survey_id.id,
            "obligation": self.learning_exam_obligation,
            "prerequisites": self.learning_prerequisite_ids.ids,
            "title": self.name,
        }

    def _generate_certification_url(self):
        if self.sudo().channel_id.filtered("training_course_id"):
            raise AccessError(self.env._("Use the private contextual mock exam."))
        return super()._generate_certification_url()


class Requirement(models.Model):
    _name = "training.elearning.exam.requirement"
    _description = "Frozen Autonomous Exam Obligation"
    membership_id = fields.Many2one(
        "slide.channel.partner", required=True, ondelete="restrict", readonly=True, index=True
    )
    company_id = fields.Many2one(related="membership_id.channel_id.learning_company_id", store=True)
    slide_id = fields.Many2one("slide.slide", required=True, ondelete="restrict", readonly=True)
    exam_id = fields.Many2one("survey.survey", required=True, ondelete="restrict", readonly=True)
    obligation = fields.Selection(OBLIGATIONS, required=True, readonly=True)
    _one_requirement = models.Constraint(
        "UNIQUE(membership_id, slide_id)", "This membership already has this exam obligation."
    )

    @api.model_create_multi
    def create(self, vals_list):  # pylint: disable=method-required-super
        raise AccessError(self.env._("Exam obligations are fixed by controlled activation."))

    def write(self, vals):  # pylint: disable=method-required-super
        raise AccessError(self.env._("Keep the frozen exam obligations."))

    @api.ondelete(at_uninstall=False)
    def _keep_requirement(self):
        raise AccessError(self.env._("Keep the frozen exam obligations."))

    @api.private
    def _capture(self, membership):
        membership.channel_id._learning_staff(manager=True)
        vals = []
        for item in membership.sudo().learning_plan["slides"]:
            if item["kind"] != "exam":
                continue
            slide = self.env["slide.slide"].sudo().browse(item["id"]).exists()
            exam = self.env["survey.survey"].sudo().browse(item["exam"]).exists()
            if (
                not slide
                or slide.channel_id != membership.channel_id
                or not exam
                or not exam.active
                or exam.training_state != "published"
                or exam.mock_company_id != membership.channel_id.learning_company_id
                or exam.training_course_id != membership.channel_id.training_course_id
            ):
                raise ValidationError(self.env._("Resolve unavailable contracted exam versions before activation."))
            vals.append(
                {
                    "membership_id": membership.id,
                    "slide_id": slide.id,
                    "exam_id": exam.id,
                    "obligation": item["obligation"],
                }
            )
        if vals:
            return super(Requirement, self.sudo().with_context({})).create(vals)  # pylint: disable=super-method-mismatch,context-overridden
        return self.browse()


class Membership(models.Model):
    _inherit = "slide.channel.partner"

    @api.private
    def _learning_freeze(self):
        result = super()._learning_freeze()
        # Coordination can activate a preconfigured course without gaining the
        # author role on its questions or the reader role on exam responses.
        self.sudo().channel_id.slide_ids._learning_check_exam()
        self.env["training.elearning.exam.requirement"]._capture(self)
        return result

    @api.private
    def _learning_plan(self):
        plan = super()._learning_plan()
        # Existing typed obligations remain authoritative on update. No native
        # membership or answer is rewritten to populate the new plan field.
        requirements = self.env["training.elearning.exam.requirement"].sudo().search([("membership_id", "=", self.id)])
        frozen = {row.slide_id.id: row for row in requirements}
        if not self.learning_plan:
            # Pre-existing memberships only had typed exam obligations. An
            # archived source must not silently erase their required evidence.
            present = {item["id"] for item in plan["slides"]}
            plan["slides"].extend(
                {
                    "id": row.slide_id.id,
                    "kind": "exam",
                    "title": row.slide_id.name,
                    "required": row.obligation != "optional",
                    "exam": row.exam_id.id,
                    "obligation": row.obligation,
                    "prerequisites": [],
                }
                for row in requirements
                if row.slide_id.id not in present
            )
        for item in plan["slides"]:
            if item["kind"] == "exam" and item["id"] in frozen:
                row = frozen[item["id"]]
                item.update(exam=row.exam_id.id, obligation=row.obligation, required=row.obligation != "optional")
        return plan


class LearningService(models.AbstractModel):
    _inherit = "training.elearning.service"

    @api.private
    def _item_status(self, member, item):
        if item["kind"] != "exam":
            return super()._item_status(member, item)
        service = self.env["training.elearning.exam.service"]
        row = service._requirement(member, item["id"])
        status = service._requirement_status(row)
        unavailable = super()._item_status(member, item)["unavailable"]
        return {
            "complete": status["satisfied"],
            "state": "done" if status["satisfied"] else ("unavailable" if unavailable else "todo"),
            "unavailable": unavailable,
            "score": status["score"],
        }

    @api.private
    def _activity_url(self, member, item):
        if item["kind"] == "exam":
            return "/my/learning/%s/exams/%s" % (member.id, item["id"])
        return super()._activity_url(member, item)


class Attempt(models.Model):
    _inherit = "survey.user_input"
    learning_membership_id = fields.Many2one(
        "slide.channel.partner", readonly=True, ondelete="restrict", copy=False, index=True
    )
    learning_slide_id = fields.Many2one("slide.slide", readonly=True, ondelete="restrict", copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if any(any(k.startswith("learning_") for k in vals) for vals in vals_list) or any(
            k.startswith("default_learning_") for k in self.env.context
        ):
            raise AccessError(self.env._("Use the private contextual mock exam."))
        return super().create(vals_list)

    def write(self, vals):
        if self.sudo().filtered("learning_membership_id") or any(k.startswith("learning_") for k in vals):
            raise AccessError(self.env._("Exam evidence is generated by the server."))
        return super().write(vals)

    def _check_for_failed_attempt(self):
        return super(Attempt, self.filtered(lambda a: not a.learning_membership_id))._check_for_failed_attempt()

    @api.private
    def _training_finish(self):
        result = super()._training_finish()
        self.sudo().learning_membership_id._learning_sync_progress()
        return result

    @api.ondelete(at_uninstall=False)
    def _keep_learning_attempt(self):
        if self.sudo().filtered("learning_membership_id"):
            raise AccessError(self.env._("Keep the native learning exam history."))


class ExamService(models.AbstractModel):
    _name = "training.elearning.exam.service"
    _inherit = "training.mock.exam.service"
    _description = "Autonomous Contextual Mock Exams"

    @api.private
    def _requirement(self, member, slide_id):
        row = (
            self.env["training.elearning.exam.requirement"]
            .sudo()
            .search([("membership_id", "=", member.id), ("slide_id", "=", slide_id)], limit=1)
        )
        if (
            not row
            or row.exam_id.training_course_id != member.channel_id.training_course_id
            or row.company_id != member.channel_id.learning_company_id
        ):
            raise AccessError(self.env._("This private exam is unavailable."))
        return row

    @api.private
    def _requirement_status(self, row):
        return self._obligation_status(
            row.exam_id,
            "slide.channel.partner:%s" % row.membership_id.id,
            row.membership_id.partner_id.id,
            row.obligation,
        )

    @api.private
    def _start(self, membership_id, slide_id):
        member, _slide, _item = self.env["training.elearning.service"]._activity(membership_id, slide_id, lock=True)
        row = self._requirement(member, slide_id)
        attempt = self._start_native(
            row.exam_id,
            "slide.channel.partner:%s" % member.id,
            {
                "learning_membership_id": member.id,
                "learning_slide_id": row.slide_id.id,
                "mock_reader_group_id": self.env.ref("training_elearning_survey.group_learning_exam_reader").id,
            },
        )
        if attempt.survey_id != row.exam_id:
            raise ValidationError(self.env._("Finish the active family attempt before changing versions."))
        return attempt

    @api.private
    def _attempt(self, attempt_id, *, mutate=False):
        attempt = self.env["survey.user_input"].sudo().browse(attempt_id).exists()
        if not attempt or not attempt.learning_membership_id:
            raise AccessError(self.env._("This private exam is unavailable."))
        member = self.env["training.elearning.service"]._membership(
            attempt.learning_membership_id.id, history=True, lock=mutate
        )
        row = self._requirement(member, attempt.learning_slide_id.id)
        if attempt.mock_context_key != "slide.channel.partner:%s" % member.id or attempt.survey_id != row.exam_id:
            raise AccessError(self.env._("This private exam is unavailable."))
        if member.learning_ends_at <= fields.Datetime.now():
            if not mutate:
                raise AccessError(self.env._("Detailed exam content is closed after access expiry."))
            attempt.lock_for_update()
            attempt.invalidate_recordset()
            if attempt.state != "done":
                attempt._training_finish()
        else:
            self.env["training.elearning.service"]._activity(member.id, attempt.learning_slide_id.id)
            if mutate or attempt.state != "done":
                attempt._mock_close_if_expired()
        return attempt

    @api.private
    def _result_images(self, attempt, question):
        return [
            {
                "label": choice.value_label,
                "url": "/my/learning-exams/%s/image/%s/%s" % (attempt.id, question.id, choice.id),
            }
            for choice in question.suggested_answer_ids
            if choice.value_image
        ]
