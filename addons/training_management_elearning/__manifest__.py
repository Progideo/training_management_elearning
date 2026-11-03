{
    "name": "Training Management — eLearning",
    "summary": "Private formative resources and enriched native mock exams",
    "version": "20.0.3.0.0",
    "category": "Services/Training",
    "author": "Training Management contributors",
    "license": "LGPL-3",
    "depends": ["training_interactive", "training_management", "training_management_survey"],
    "data": ["security/groups.xml", "security/ir.access.csv", "views/resource_views.xml", "views/editorial_views.xml", "views/runtime_views.xml", "views/enriched_views.xml"],
    "assets": {"web.assets_frontend": ["training_management_elearning/static/src/enriched.js"]},
    "installable": True,
    "application": False,
}
