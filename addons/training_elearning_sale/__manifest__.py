# pylint: disable=manifest-required-author,missing-readme  # non-OCA; documentation in docs/
{
    "name": "Training eLearning — Sales",
    "summary": "Native sales, named seats and controlled autonomous access",
    "version": "20.0.1.7.0",
    "category": "Sales/Sales",
    "author": "Training Management contributors",
    "website": "https://github.com/Progideo/training_management_elearning",
    "license": "LGPL-3",
    "depends": ["training_elearning", "sale_management"],
    "data": [
        "security/groups.xml",
        "security/ir.access.csv",
        "data/mail.xml",
        "data/purchase_reports.xml",
        "views/sale_views.xml",
        "views/path_sale_views.xml",
        "views/mandate_views.xml",
        "views/purchase_reports.xml",
    ],
}
