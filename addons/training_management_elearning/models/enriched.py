"""TM passation adapter for the common enriched question definitions."""
from odoo import api, models
from odoo.exceptions import ValidationError


class Survey(models.Model):
    _inherit = 'survey.survey'

    def action_training_publish(self):
        self._training_edit()
        self.question_ids._validate_interaction()
        return super().action_training_publish()


class ExamService(models.AbstractModel):
    _inherit = 'training.exam.service'

    @api.private
    def _save(self,attempt_id,question_id,choices,marked):
        candidate=self.env['survey.question'].sudo().browse(question_id).exists()
        if not candidate or not candidate.training_interaction:
            return super()._save(attempt_id,question_id,choices,marked)
        attempt=self._attempt(attempt_id,mutate=True)
        if attempt.state!='done':
            question=attempt.predefined_question_ids.filtered(lambda q:q.id==question_id)
            if question.training_interaction:
                if not isinstance(choices,list) or any(type(c) is not int for c in choices):
                    raise ValidationError('Invalid interaction answer')
                selected=question.suggested_answer_ids.filtered(lambda a:a.id in choices)
                if (len(selected)!=len(choices) or len(set(selected.mapped('training_row_key')))!=len(selected)
                        or len(set(selected.mapped('training_option_key')))!=len(selected)):
                    raise ValidationError(self.env._('Assign each item at most once; leave unanswered rows empty.'))
        # Reuse native deadline, answer storage, exact all-or-nothing scoring and review.
        return super()._save(attempt_id,question_id,choices,marked)
