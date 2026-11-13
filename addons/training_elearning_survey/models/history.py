"""Global and theme scores only: expired history never returns questions or corrections."""

from odoo import api, models


class Service(models.AbstractModel):
    _inherit = "training.elearning.service"  # pylint: disable=consider-merging-classes-inherited
    # Closed history exposes only scalar results, independently of live access.

    @api.private
    def _history_entries(self, member, item):
        if item["kind"] != "exam":
            return super()._history_entries(member, item)
        service = self.env["training.elearning.exam.service"]
        requirement = service._requirement(member, item["id"])
        attempts = (
            self.env["survey.user_input"]
            .sudo()
            .search(
                [
                    ("learning_membership_id", "=", member.id),
                    ("learning_slide_id", "=", item["id"]),
                    ("survey_id", "=", requirement.exam_id.id),
                    ("mock_context_key", "=", "slide.channel.partner:%s" % member.id),
                ],
                order="id desc",
            )
        )
        result = []
        for attempt in attempts:
            entry = {"date": attempt.end_datetime or attempt.create_date, "url": False, "themes": []}
            if attempt.learning_interrupted_at:
                entry["label"] = "Examen interrompu ; aucun échec pédagogique ajouté"
            elif attempt.state != "done":
                entry["label"] = "Tentative non terminée ; aucun score final disponible"
            else:
                revisions = service._result_adjustments(attempt)
                entry.update(self._exam_history_score(attempt))
                result.append(entry)
                for revision in revisions.sorted("id"):
                    result.append(self._exam_history_score(attempt, revision))
                continue
            result.append(entry)
        return result

    @api.private
    def _exam_history_score(self, attempt, revision=None):
        themes, points, maximum = {}, 0, 0
        for row in attempt._training_scores():
            question = row["question"]
            obtained = revision.points_by_question[str(question.id)] if revision else row["points"]
            theme = question.training_theme or question.page_id.title or self.env._("Unclassified")
            totals = themes.setdefault(theme, {"points": 0, "maximum": 0})
            totals["points"] += obtained
            totals["maximum"] += row["maximum"]
            points += obtained
            maximum += row["maximum"]
        # A free-text correction reason can contain pedagogical detail. Closed
        # history keeps only the revision date and global/theme totals.
        return {
            "label": ("Score révisé : %g / %g" if revision else "Score global : %g / %g") % (points, maximum),
            "date": (revision.revised_at or revision.create_date) if revision else attempt.end_datetime,
            "url": False,
            "themes": [{"name": name, **totals} for name, totals in themes.items()],
        }
