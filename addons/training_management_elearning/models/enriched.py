"""Matching and ordering use exact native multi-choice edges, never client scores."""
import secrets
from odoo import api, fields, models, Command
from odoo.exceptions import ValidationError


class Question(models.Model):
    _inherit = 'survey.question'
    training_interaction = fields.Selection([('matching','Appariement'),('ordering','Mise en ordre')],copy=True)

    training_interaction_solution = fields.Text(compute='_compute_interaction_solution', groups='training_management.group_training_coordinator')

    @api.depends('suggested_answer_ids.is_correct', 'suggested_answer_ids.training_row_label', 'suggested_answer_ids.training_option_label')
    def _compute_interaction_solution(self):
        for question in self:
            question.training_interaction_solution = '\n'.join(
                a.training_row_label + ' → ' + a.training_option_label
                for a in question.suggested_answer_ids.filtered(lambda a: a.is_correct and a.training_row_label and a.training_option_label).sorted('training_row_key'))

    @api.private
    def _interaction_rows(self):
        self.ensure_one()
        # Explicit allow-list: no correctness flags, scores or solution order here.
        answers=self.suggested_answer_ids
        rows=[]
        for key in sorted(set(answers.mapped('training_row_key'))):
            choices=answers.filtered(lambda a:a.training_row_key==key)
            rows.append({'key':key,'label':choices[:1].training_row_label,
                'choices':[{'id':a.id,'label':a.training_option_label,'option':a.training_option_key}
                    for a in choices.sorted(lambda a:(a.training_option_label,a.training_option_key))]})
        return rows

    @api.private
    def _validate_interaction(self):
        for question in self.filtered('training_interaction'):
            exam=question.survey_id
            if (not exam.training_program_id or exam.training_evaluation_id or exam.training_feedback_id
                    or question.question_type!='multiple_choice'):
                raise ValidationError(self.env._('Use enriched interactions only in an explicitly configured mock exam.'))
            answers=question.suggested_answer_ids
            rows=set(answers.mapped('training_row_key'));options=set(answers.mapped('training_option_key'))
            if not 2<=len(rows)==len(options)<=8 or not all(rows) or not all(options) or len(answers)!=len(rows)*len(options):
                raise ValidationError(self.env._('Configure a complete interaction of two to eight distinct items.'))
            cells={(a.training_row_key,a.training_option_key) for a in answers}
            if len(cells)!=len(answers):
                raise ValidationError(self.env._('Each row and option pair must be unique.'))
            for key in rows:
                group=answers.filtered(lambda a:a.training_row_key==key)
                if len(set(group.mapped('training_row_label')))!=1 or not group[0].training_row_label:
                    raise ValidationError(self.env._('Keep a single non-empty label per row.'))
            for key in options:
                group=answers.filtered(lambda a:a.training_option_key==key)
                if len(set(group.mapped('training_option_label')))!=1 or not group[0].training_option_label:
                    raise ValidationError(self.env._('Keep a single non-empty label per option.'))
            correct=answers.filtered('is_correct')
            if len(correct)!=len(rows) or set(correct.mapped('training_row_key'))!=rows or set(correct.mapped('training_option_key'))!=options:
                raise ValidationError(self.env._('The solution must use each item exactly once.'))
            if len({a.training_row_label for a in correct})!=len(rows) or len({a.training_option_label for a in correct})!=len(options):
                raise ValidationError(self.env._('Use distinct row and option labels.'))

    @api.private
    def _configure_interaction(self,kind,items):
        self.ensure_one()
        self.survey_id._training_edit()
        if kind not in ('matching','ordering'):
            raise ValidationError(self.env._('Choose matching or ordering.'))
        lines=[line.strip() for line in items.splitlines() if line.strip()]
        if not 2<=len(lines)<=8:
            raise ValidationError(self.env._('Enter two to eight items.'))
        if kind=='matching':
            pairs=[line.split('|') for line in lines]
            if any(len(p)!=2 or not all(v.strip() for v in p) for p in pairs):
                raise ValidationError(self.env._('Use one left | right pair per line.'))
            pairs=[(left.strip(),right.strip()) for left,right in pairs]
        else:
            pairs=[('Position %s'%(i+1),line) for i,line in enumerate(lines)]
        if any(len(v)>160 for pair in pairs for v in pair):
            raise ValidationError(self.env._('Keep item labels under 160 characters.'))
        options=[(secrets.token_hex(12),right) for left,right in pairs]
        # Random identifiers and alphabetic display disclose no solution index.
        definitions=[]
        for i,(left,right) in enumerate(pairs):
            for key,label in sorted(options,key=lambda option:option[1]):
                definitions.append(Command.create({'value':left+' → '+label,'is_correct':label==right,
                    'training_row_key':'r%02d'%i,'training_row_label':left,
                    'training_option_key':key,'training_option_label':label}))
        self.write({'question_type':'multiple_choice','training_interaction':kind,
            'suggested_answer_ids':[*[Command.delete(a.id) for a in self.suggested_answer_ids],*definitions]})
        self._validate_interaction()
        return True


class Choice(models.Model):
    _inherit = 'survey.question.answer'
    training_row_key = fields.Char(copy=True)
    training_row_label = fields.Char(copy=True)
    training_option_key = fields.Char(copy=True)
    training_option_label = fields.Char(copy=True)


class Survey(models.Model):
    _inherit = 'survey.survey'

    def action_training_publish(self):
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


class Configure(models.TransientModel):
    _name = 'training.elearning.question.configure'
    _description = 'Configure Enriched Exam Question'
    question_id = fields.Many2one('survey.question',required=True)
    kind = fields.Selection([('matching','Appariement'),('ordering','Mise en ordre')],required=True)
    items = fields.Text(required=True,string='Éléments',help='Appariement : gauche | droite, une paire par ligne. Mise en ordre : un élément par ligne, dans l’ordre correct.')

    def action_configure(self):
        self.ensure_one()
        self.check_access('read')
        self.question_id._configure_interaction(self.kind,self.items)
        return {'type':'ir.actions.act_window_close'}
