import io
import json
import zipfile
from datetime import timedelta
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from .test_attempt import RuntimeCase
from .test_content_security import ContentCase
from odoo.addons.training_management_survey.tests.test_exam import ExamCase
from ..services.archive import parse_package


def h5p(files=None):
    data = {
        'h5p.json': json.dumps({'mainLibrary':'H5P.TrueFalse','preloadedDependencies':[
            {'machineName':'H5P.TrueFalse','majorVersion':'1','minorVersion':'8'}]}),
        'content/content.json': json.dumps({'correct':'true','question':'Fictional question'}),
    }
    data.update(files or {})
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        for key,value in data.items():archive.writestr(key,value)
    return stream.getvalue()


@tagged('post_install','-at_install')
class TestReviewContent(ContentCase):
    def test_withdrawal_keeps_first_decision(self):
        version=self.version().with_user(self.coord)
        version._withdraw('First decision')
        with self.assertRaises(ValidationError):version._withdraw('Overwrite attempt')
        self.assertEqual(version.withdrawal_reason,'First decision')
        self.assertEqual(version.withdrawn_by_id,self.coord)
        self.assertTrue(version.withdrawn_at)

    def test_h5p_missing_runtime_and_malformed_shapes(self):
        for files in ({},{'h5p.json':'[]'},{'h5p.json':'null'},
                      {'content/content.json':'[]'},{'h5p.json':json.dumps({'mainLibrary':'H5P.TrueFalse','preloadedDependencies':[None]})}):
            with self.subTest(files=files), self.assertRaises(ValueError):parse_package(h5p(files),'h5p')

    def test_lease_cleanup_preserves_live_authorizations(self):
        version=self.version()
        service=self.env['training.elearning.lease'].with_user(self.author)
        expired,_=service._issue(version)
        live,token=service._issue(version)
        self.env.cr.execute('UPDATE training_elearning_lease SET expires_at=%s WHERE id=%s',
            [fields.Datetime.now()-timedelta(days=2),expired.id])
        self.env['training.elearning.lease']._gc_expired()
        self.assertFalse(expired.exists())
        self.assertEqual(service._resolve(token),live)
        self.assertTrue(version.exists())

    def test_h5p_assets_and_runtime_graph(self):
        library={'machineName':'H5P.TrueFalse','majorVersion':1,'minorVersion':8,
                 'preloadedJs':[{'path':'main.js'}]}
        files={'H5P.TrueFalse-1.8/library.json':json.dumps(library),'H5P.TrueFalse-1.8/main.js':'// fixture'}
        self.assertEqual(parse_package(h5p(files),'h5p')['entrypoint'],'h5p.json')
        for broken in ({**files,'H5P.TrueFalse-1.8/library.json':json.dumps({**library,'minorVersion':9})},
                       {'H5P.TrueFalse-1.8/library.json':json.dumps(library)},
                       {**files,'H5P.TrueFalse-1.8/library.json':json.dumps({**library,'preloadedDependencies':[library]})}):
            with self.assertRaises(ValueError):parse_package(h5p(broken),'h5p')


@tagged('post_install','-at_install')
class TestReviewRuntime(RuntimeCase):
    def test_extreme_numeric_result_is_validation_error(self):
        enrollment,usage=self.setup_runtime()
        attempt=self.start(enrollment,usage)
        with self.assertRaises(ValidationError):
            attempt._save('huge',1,{'result':{'score':10**400,'maximum':10**401,'completed':True}})
        self.assertFalse(attempt.sudo().event_ids)
        self.assertEqual(attempt.sudo().revision,0)

    def test_defaults_cannot_forge_internal_records(self):
        enrollment,usage=self.setup_runtime()
        attempt=self.env['training.elearning.attempt'].with_user(self.portal).with_context(
            default_revision=99,default_completed=True,default_state_json='{"forged":true}')._start(enrollment.id,usage.id,'review-safe-launch')
        self.assertEqual(attempt._snapshot()['revision'],0)
        self.assertEqual(attempt._snapshot()['state'],{})
        with self.assertRaises(AccessError):
            self.service()._progress(enrollment,usage.activity_id,create=True).with_user(self.coordinator).write({'elearning_completed':True})


@tagged('post_install','-at_install')
class TestReviewQuestions(ExamCase):
    def test_configuration_failure_is_atomic(self):
        exam,question,_=self.exam()
        before=question.suggested_answer_ids.ids
        # Caller may handle the validation error; the original definition must survive.
        try:
            question._configure_interaction('matching','A | X\nB | X')
        except ValidationError:
            pass
        else:
            self.fail('Duplicate option accepted')
        self.assertFalse(question.training_interaction)
        self.assertEqual(question.suggested_answer_ids.ids,before)

    def test_enriched_definition_cannot_publish_as_regular_question(self):
        exam,question,_=self.exam()
        question._configure_interaction('ordering','Prepare\nExecute')
        question.question_type='simple_choice'
        with self.assertRaises(ValidationError):exam.action_training_publish()

    def test_publication_rejects_conflicting_correction_labels(self):
        exam,question,_=self.exam()
        question._configure_interaction('ordering','Prepare\nExecute')
        question.suggested_answer_ids[:1].value='A different correction'
        with self.assertRaises(ValidationError):exam.action_training_publish()
