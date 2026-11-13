"""Native lessons and evidence; the frozen plan contains pedagogy, never a second score store."""

import copy
import re
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import is_html_empty


class Course(models.Model):
    _inherit = "slide.channel"  # pylint: disable=consider-merging-classes-inherited  # lesson semantics are separate from the native boundary

    @api.private
    def _learning_related_courses(self, *, ancestors=False):
        result = self.sudo().with_context(active_test=False)
        frontier = result
        while frontier:
            adjacent = (
                frontier.prerequisite_channel_ids
                if ancestors
                else self.sudo()
                .with_context(active_test=False)
                .search([("training_course_id", "!=", False), ("prerequisite_channel_ids", "in", frontier.ids)])
            )
            frontier = adjacent - result
            result |= frontier
        return result

    @api.private
    def _learning_lock_graph(self):
        self.lock_for_update()
        self._learning_related_courses(ancestors=True).lock_for_update()

    @api.private
    def _learning_check_graph(self):
        for course in self:
            slides = course.slide_ids.filtered(lambda s: not s.is_category)
            for slide in slides:
                if any(
                    p.channel_id != course or p.is_category or not p.is_published or not p.active
                    for p in slide.learning_prerequisite_ids
                ):
                    raise ValidationError(self.env._("Choose published lesson prerequisites from this course."))
                seen = set()

                def visit(item, chain):
                    if item.id in chain:
                        raise ValidationError(self.env._("Lesson prerequisites must not contain a cycle."))
                    if item.id in seen:
                        return
                    seen.add(item.id)
                    for parent in item.learning_prerequisite_ids:
                        if slide._learning_plan_item()["required"] and not parent._learning_plan_item()["required"]:
                            raise ValidationError(
                                self.env._("An optional lesson cannot be a prerequisite of a required lesson.")
                            )
                        visit(parent, chain | {item.id})

                visit(slide, set())
            visited = set()

            def course_visit(item, chain):
                if item.id in chain:
                    raise ValidationError(self.env._("Course prerequisites must not contain a cycle."))
                if item.id in visited:
                    return
                visited.add(item.id)
                for parent in item.prerequisite_channel_ids:
                    if (
                        not parent.training_course_id
                        or parent.learning_company_id != course.learning_company_id
                        or parent.learning_state != "published"
                        or not parent.active
                    ):
                        raise ValidationError(
                            self.env._("Choose published prerequisite courses from the same operating company.")
                        )
                    course_visit(parent, chain | {item.id})

            course_visit(course, set())

    @api.private
    def _learning_plan(self):
        self.ensure_one()
        return {
            "slides": [
                slide._learning_plan_item()
                for slide in self.sudo().slide_ids
                if not slide.is_category and slide.active and slide.is_published
            ],
            "courses": self.prerequisite_channel_ids.ids,
        }


class Slide(models.Model):
    _inherit = "slide.slide"  # pylint: disable=consider-merging-classes-inherited
    learning_optional = fields.Boolean(string="Optional Activity")
    learning_prerequisite_ids = fields.Many2many(
        "slide.slide", "learning_slide_prerequisite_rel", "slide_id", "prerequisite_id", string="Lesson Prerequisites"
    )
    learning_filename = fields.Char()
    learning_public_video = fields.Boolean(string="Intentionally Public Video")

    @api.private
    def _learning_supported(self):
        self.ensure_one()
        if not self.is_published or not self.active:
            return False
        if self.slide_category == "article":
            return not is_html_empty(self.html_content)
        if self.slide_category == "document":
            return self.source_type == "local_file" and bool(
                self.binary_content and self._get_completion_time_pdf(self.binary_content.content)
            )
        if self.slide_category == "video":
            return bool(
                self.learning_public_video
                and self.video_source_type in ("youtube", "vimeo")
                and (
                    re.fullmatch(r"[A-Za-z0-9_-]+", self.youtube_id or "")
                    if self.video_source_type == "youtube"
                    else re.fullmatch(r"\d+", self.vimeo_id or "")
                )
            )
        return super()._learning_supported()

    @api.private
    def _learning_plan_item(self):
        self.ensure_one()
        kind = {"document": "pdf", "article": "article", "video": "video"}.get(self.slide_category)
        if not kind:
            raise ValidationError(self.env._("This activity needs a supported learning adapter."))
        return {
            "id": self.id,
            "kind": kind,
            "required": not self.learning_optional,
            "prerequisites": self.learning_prerequisite_ids.ids,
            "title": self.name,
        }


class Membership(models.Model):
    _inherit = "slide.channel.partner"  # pylint: disable=consider-merging-classes-inherited
    learning_plan = fields.Json(readonly=True, copy=False)

    @api.private
    def _learning_plan(self):
        self.ensure_one()
        plan = copy.deepcopy(self.sudo().learning_plan or self.sudo().channel_id._learning_plan())
        slides = self.env["slide.slide"].sudo().browse([item["id"] for item in plan["slides"]]).exists()
        titles = {slide.id: slide.name for slide in slides}
        for item in plan["slides"]:
            item["title"] = titles.get(item["id"], item["title"])
        return plan

    @api.private
    def _learning_freeze(self):
        self.channel_id._learning_lock_graph()
        self.channel_id._learning_check_contents()
        self.channel_id._learning_bind_graph()
        result = super()._learning_freeze()
        self._learning_store({"learning_plan": self._learning_plan_source()})
        return result

    @api.private
    def _learning_plan_source(self):
        return self.channel_id._learning_plan()

    @api.private
    def _learning_progress(self):
        self.ensure_one()
        items = self._learning_plan()["slides"]
        required = [item for item in items if item["required"]]
        service = self.env["training.elearning.service"]
        satisfied = sum(service._item_status(self, item)["complete"] for item in required)
        return {
            "required": len(required),
            "satisfied": satisfied,
            "percentage": round(100 * satisfied / len(required)) if required else 100,
            "complete": satisfied == len(required),
        }

    @api.private
    def _learning_sync_progress(self):
        for member in self.filtered("learning_started_at"):
            for item in member._learning_plan()["slides"]:
                status = self.env["training.elearning.service"]._item_status(member, item)
                if item["kind"] not in ("article", "pdf", "video"):
                    self.env["slide.slide.partner"]._learning_project(member, item["id"], status["complete"])
        return super()._learning_sync_progress()


class Service(models.AbstractModel):
    _inherit = "training.elearning.service"

    @api.private
    def _activity_url(self, member, item):
        return "/my/learning/%s/activities/%s" % (member.id, item["id"])

    @api.private
    def _item_status(self, member, item):
        row = (
            self.env["slide.slide.partner"]
            .sudo()
            .search([("slide_id", "=", item["id"]), ("partner_id", "=", member.partner_id.id)], limit=1)
        )
        slide = self.env["slide.slide"].sudo().browse(item["id"]).exists()
        unavailable = not slide or not slide._learning_available()
        invalidation = self.env["training.elearning.acquisition.invalidation"]._latest(member, item["id"])
        return {
            "complete": bool(row.completed),
            "state": "done" if row.completed else ("unavailable" if unavailable else "todo"),
            "unavailable": unavailable,
            "acquisition_invalidated": bool(invalidation and not invalidation.restored_at),
            "invalidated_at": invalidation.invalidated_at if invalidation else False,
        }

    @api.private
    def _course_prerequisites(self, member):
        for course_id in member._learning_plan().get("courses", []):
            previous = (
                self.env["slide.channel.partner"]
                .sudo()
                .with_context(active_test=False)
                .search([("channel_id", "=", course_id), ("partner_id", "=", member.partner_id.id)], limit=1)
            )
            if not previous.learning_started_at or not previous._learning_progress()["complete"]:
                return False
        return True

    @api.private
    def _activity(self, membership_id, slide_id, *, lock=False):
        member = self._membership(membership_id, lock=lock)
        item = next((i for i in member._learning_plan()["slides"] if i["id"] == slide_id), None)
        slide = self.env["slide.slide"].sudo().browse(slide_id).exists()
        if (
            not item
            or not slide
            or slide.channel_id != member.channel_id
            or not slide.active
            or not slide.is_published
            or not slide._learning_available()
            or not self._course_prerequisites(member)
        ):
            raise AccessError(self.env._("This private learning activity is unavailable."))
        for prerequisite in item.get("prerequisites", []):
            parent = next((i for i in member._learning_plan()["slides"] if i["id"] == prerequisite), None)
            if not parent or not self._item_status(member, parent)["complete"]:
                raise AccessError(self.env._("Complete the explicit lesson prerequisites first."))
        return member, slide, item

    @api.private
    def _declare(self, membership_id, slide_id):
        member, slide, item = self._activity(membership_id, slide_id, lock=True)
        if item["kind"] not in ("article", "pdf", "video"):
            raise AccessError(self.env._("This activity requires its own server completion evidence."))
        self.env["slide.slide.partner"]._learning_project(member, slide.id, True)
        member._learning_sync_progress()
        return True


class Catalog(models.Model):
    _inherit = "training.course"

    def write(self, vals):
        if "company_id" in vals and any(c.company_id.id != vals["company_id"] for c in self):
            self.lock_for_update()
            if (
                self.env["slide.channel"]
                .sudo()
                .with_context(active_test=False)
                .search_count([("training_course_id", "in", self.ids)])
            ):
                raise ValidationError(self.env._("Keep the operating company of referenced course editions."))
        return super().write(vals)
