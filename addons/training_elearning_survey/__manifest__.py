# pylint: disable=manifest-required-author,missing-readme  # non-OCA module; documentation in docs/
{
    "name": "Training eLearning — Shared Mock Exams",
    "summary": "Native course exam obligations and contextual attempts",
    "version": "20.0.1.1.0",
    "category": "Website/eLearning",
    "author": "Training Management contributors",
    "website": "https://github.com/Progideo/training_management_elearning",
    "license": "LGPL-3",
    "depends": ["training_elearning", "training_mock_exam", "website_slides_survey"],
    "data": ["security/groups.xml", "security/ir.access.csv", "views/exam_views.xml", "views/portal.xml"],
}
