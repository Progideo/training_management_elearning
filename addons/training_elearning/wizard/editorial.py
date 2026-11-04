"""An author's explicit claim of a superficial correction, with immutable trace."""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Editorial(models.TransientModel):
    _name = "training.elearning.editorial"
    _description = "Audited Superficial Course Correction"
    course_id = fields.Many2one("slide.channel", required=True)
    slide_id = fields.Many2one("slide.slide")
    category = fields.Selection(
        [
            ("typo", "Typographical Correction"),
            ("layout", "Layout"),
            ("accessibility", "Accessibility"),
            ("link", "Equivalent Link"),
        ],
        required=True,
    )
    reason = fields.Text(required=True)
    name = fields.Char(required=True)
    html_content = fields.Html()
    binary_content = fields.Binary()
    filename = fields.Char()
    video_url = fields.Char()
    slide_category = fields.Selection(related="slide_id.slide_category")

    @api.model
    def default_get(self, names):
        values = super().default_get(names)
        course = self.env["slide.channel"].browse(values.get("course_id"))
        slide = self.env["slide.slide"].browse(values.get("slide_id"))
        if slide:
            course = slide.channel_id
        if course:
            course._learning_staff()
            values.update(
                course_id=course.id,
                name=slide.name if slide else course.name,
                html_content=slide.html_content if slide else course.description_html,
                filename=slide.learning_filename if slide else False,
                video_url=slide.video_url if slide else False,
            )
        return {key: value for key, value in values.items() if key in names}

    def action_apply(self):
        self.ensure_one()
        self.course_id._learning_staff()
        if self.slide_id:
            slide = self.slide_id
            if slide.channel_id != self.course_id:
                raise ValidationError(self.env._("Choose an activity from this course."))
            values = {"name": self.name}
            if slide.slide_category == "article":
                values["html_content"] = self.html_content
            elif slide.slide_category == "document":
                values["learning_filename"] = self.filename
                if self.binary_content:
                    values["binary_content"] = self.binary_content
            elif slide.slide_category == "video":
                values["video_url"] = self.video_url
            slide._learning_apply_editorial(values, self.reason, self.category)
        else:
            self.course_id._learning_apply_editorial(
                {"name": self.name, "description_html": self.html_content}, self.reason, self.category
            )
        return {"type": "ir.actions.act_window_close"}
