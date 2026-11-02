from datetime import timedelta
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.addons.training_management_survey.tests.test_exam import ExamCase


@tagged('post_install', '-at_install')
class TestEnriched(ExamCase):
    def prepared(self):
        exam, matching, ordering = self.exam()
        matching._configure_interaction('matching', 'Chat | Cat\nChien | Dog\nOiseau | Bird')
        ordering._configure_interaction('ordering', 'Préparer\nExécuter\nVérifier')
        exam.action_training_publish()
        delivery = self.delivery()
        activity = self.env['training.learning.activity'].with_user(self.coordinator).create({
            'name': 'Enriched exam', 'delivery_id': delivery.id, 'criterion': 'evaluation',
            'evaluation_threshold': 75, 'training_exam_id': exam.id})
        enrollment = self.opened(delivery)
        service = self.env['training.exam.service'].with_user(self.portal)
        return exam, matching, ordering, activity, enrollment, service

    def test_exact_partial_wrong_empty_and_resume(self):
        exam, matching, ordering, activity, enrollment, service = self.prepared()
        correct = [q.suggested_answer_ids.filtered('is_correct').ids for q in (matching, ordering)]
        # Four real passations: exact, partial, wrong permutation, empty.
        for mode, expected in [('exact', 24), ('partial', 0), ('wrong', 0), ('empty', 0)]:
            attempt = service._start(enrollment.id, activity.id)
            for q, ids in zip((matching, ordering), correct):
                if mode == 'partial': ids = ids[:1]
                elif mode == 'empty': ids = []
                elif mode == 'wrong':
                    rows = q._interaction_rows()
                    solution = q.suggested_answer_ids.filtered('is_correct').sorted('training_row_key')
                    ids = [next(c['id'] for c in row['choices'] if c['option'] == solution[(i+1)%3].training_option_key) for i,row in enumerate(rows)]
                service._save(attempt.id, q.id, ids, True)
                self.assertEqual(service._start(enrollment.id, activity.id), attempt)
                selected = attempt.user_input_line_ids.filtered(lambda l:l.question_id==q).suggested_answer_id.ids
                self.assertEqual(set(selected), set(ids))
            with self.assertRaises(AccessError): service._result(attempt)
            service._submit(attempt.id)
            result = service._result(attempt)
            self.assertEqual(result['points'], expected)
            self.assertEqual(sum(t['points'] for t in result['themes'].values()), expected)
            self.assertEqual(len(result['questions'][0]['correct']), 3)
        self.assertEqual(service._result(self.env['survey.user_input'].sudo().search([('training_enrollment_id','=',enrollment.id)],order='id',limit=1))['points'], 24)

    def test_invalid_edges_cross_actor_and_deadline(self):
        exam, matching, ordering, activity, enrollment, service = self.prepared()
        attempt = service._start(enrollment.id, activity.id)
        choices = matching.suggested_answer_ids
        invalid = [choices[:2].ids, [choices[0].id, choices[3].id], [choices[0].id]*2, ordering.suggested_answer_ids[:1].ids]
        for ids in invalid:
            with self.assertRaises(ValidationError), self.cr.savepoint(): service._save(attempt.id, matching.id, ids, False)
        with self.assertRaises(AccessError): service.with_user(self.portal_b)._save(attempt.id, matching.id, [], False)
        self.assertFalse(attempt.user_input_line_ids)
        service._save(attempt.id, matching.id, choices.filtered('is_correct').ids, False)
        # Native private factory simulates elapsed time, then the same save closes the attempt.
        attempt._training_store({'deadline': fields.Datetime.now()-timedelta(seconds=1)})
        self.assertEqual(service._save(attempt.id, ordering.id, ordering.suggested_answer_ids.filtered('is_correct').ids, False), {'done':True})
        self.assertEqual(service._result(attempt)['points'], 18)

    def test_publication_freeze_revision_and_safe_render_data(self):
        exam, matching, ordering, activity, enrollment, service = self.prepared()
        for row in matching._interaction_rows():
            self.assertEqual(set(row), {'key','label','choices'})
            for choice in row['choices']: self.assertEqual(set(choice), {'id','label','option'})
        with self.assertRaises((AccessError,ValidationError)), self.cr.savepoint(): matching._configure_interaction('ordering','A\nB')
        with self.assertRaises((AccessError,ValidationError)), self.cr.savepoint(): matching.suggested_answer_ids[:1].write({'training_option_label':'Changed'})
        action = exam.action_training_new_version()
        revision = self.env['survey.survey'].with_user(self.coordinator).browse(action['res_id'])
        revised = revision.question_ids.filtered(lambda q:q.training_interaction=='matching')
        revised._configure_interaction('matching','Un | One\nDeux | Two')
        revision.write({'training_version':'2','training_revision_reason':'Fictional new wording'})
        revision.action_training_publish()
        self.assertEqual(len(matching.suggested_answer_ids),9)
        self.assertEqual(len(revised.suggested_answer_ids),4)
        self.assertEqual(activity.training_exam_id, exam)

    def test_malformed_configuration_and_native_publication_checks(self):
        for kind, items in [('matching','A | X\nB | X'), ('ordering','A\nA'), ('matching','A\nB'), ('ordering','Only one')]:
            exam,q,_ = self.exam()
            with self.assertRaises(ValidationError), self.cr.savepoint(): q._configure_interaction(kind,items)
        exam,q,_ = self.exam()
        q._configure_interaction('ordering','A\nB')
        q.suggested_answer_ids[:1].unlink()
        with self.assertRaises(ValidationError), self.cr.savepoint(): exam.action_training_publish()
        exam,q,_ = self.exam()
        q._configure_interaction('ordering','A\nB')
        q.answer_score = 0
        with self.assertRaises(ValidationError), self.cr.savepoint(): exam.action_training_publish()
