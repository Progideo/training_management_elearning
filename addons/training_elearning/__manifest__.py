# pylint: disable=manifest-required-author,missing-readme  # non-OCA module; documentation in docs/
{
    "name": "Training eLearning",
    "summary": "Private native course editions and controlled learner access",
    "version": "20.0.1.2.0",
    "category": "Website/eLearning",
    "author": "Training Management contributors",
    "website": "https://github.com/Progideo/training_management_elearning",
    "license": "LGPL-3",
    "depends": ["training_catalog", "training_interactive", "website_slides"],
    "data": [
        "security/groups.xml",
        "security/ir.access.csv",
        "wizard/access_views.xml",
        "wizard/editorial_views.xml",
        "views/course_views.xml",
        "views/portal.xml",
    ],
    "application": True,
}
