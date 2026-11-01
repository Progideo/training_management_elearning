"""Persistent fictional history, created once before two addon updates."""
from odoo.tests import new_test_user
assert env.cr.dbname == 'e00_fresh'
assert not env['training.course'].search_count([('name', '=', 'E00 fictional course')])
coord = new_test_user(env, login='e00_coord', groups='training_management.group_training_coordinator')
learner = new_test_user(env, login='e00_learner', groups='base.group_portal')
customer = env['res.partner'].create({'name': 'E00 fictional customer'})
course = env['training.course'].create({'name': 'E00 fictional course', 'company_id': env.company.id})
course.category_id = env['training.category'].create({'name': 'E00 fictional category', 'company_id': env.company.id})
program = env['training.program.version'].create({
    'course_id': course.id, 'version': 'E00-1', 'title': 'E00 fictional programme',
    'objectives': 'Practice', 'target_audience': 'Beginners', 'prerequisites': 'Reviewed',
    'content': 'Practice', 'duration_hours': 1, 'delivery_mode': 'elearning',
    'language_id': env.ref('base.lang_en').id, 'teaching_methods': 'Practice',
    'evaluation_criteria': 'Human review', 'access_conditions': 'Native admission',
    'accessibility_contact_id': customer.id, 'accessibility_information': 'Fictional contact'})
program.action_validate()
delivery = env['training.delivery'].with_user(coord).create({'name': 'E00 fictional delivery',
    'company_id': env.company.id, 'program_id': program.id, 'kind': 'autonomous',
    'capacity': 10, 'access_policy': 'duration', 'access_days': 10})
activity = env['training.learning.activity'].with_user(coord).create({'name': 'E00 historical consultation', 'delivery_id': delivery.id})
human = env['training.learning.activity'].with_user(coord).create({'name': 'E00 historical human review', 'delivery_id': delivery.id, 'criterion': 'validation'})
enrollment = env['training.enrollment'].with_user(coord).create({'delivery_id': delivery.id,
    'participant_id': learner.partner_id.id, 'user_id': learner.id, 'free_reason': 'Fictional invitation'})
enrollment.action_validate_prerequisites(reason='Fictional review')
enrollment.action_confirm()
enrollment.action_authorize(reason='Fictional authorization')
enrollment.action_open_access(reason='Fictional opening')
env['training.learning.service'].with_user(learner)._declare(enrollment.id, activity.id)
resource = env['training.elearning.resource'].with_user(coord).create({'name': 'E00 fictional resource', 'format': 'h5p', 'license_note': 'Fictional metadata; no package'})
env.cr.commit()
print('E00_SEED_OK')
