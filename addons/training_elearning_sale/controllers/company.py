from odoo import fields, http
from odoo.http import request
from odoo.exceptions import AccessError, MissingError, ValidationError, LockError
from odoo.tools import format_datetime


def private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def presentation(data):
    data = dict(data)
    data["valid_until"] = format_datetime(request.env, data["valid_until"], tz=request.env.user.tz or "UTC")
    data["rows"] = [
        dict(
            row,
            **{
                key: format_datetime(request.env, row[key], tz=request.env.user.tz or "UTC") if row[key] else ""
                for key in ("start", "end")
            },
        )
        for row in data["rows"]
    ]
    for row in data["rows"]:
        summary = row.get("summary", {})
        if summary.get("completed_at"):
            summary["completed_at"] = format_datetime(
                request.env, fields.Datetime.to_datetime(summary["completed_at"]), tz=request.env.user.tz or "UTC"
            )
    data["timezone"] = request.env.user.tz or "UTC"
    return data


class CompanyPortal(http.Controller):
    @http.route("/my/learning-purchases", type="http", auth="user", website=True, methods=["GET"])
    def purchases(self, **kw):
        values = request.env["training.elearning.company.service"]._list()
        return private(request.render("training_elearning_sale.company_purchases", {"purchases": values}))

    @http.route("/my/learning-purchases/<int:mandate_id>", type="http", auth="user", website=True, methods=["GET"])
    def purchase(self, mandate_id, **kw):
        try:
            data = request.env["training.elearning.company.service"]._view(mandate_id)
            return private(request.render("training_elearning_sale.company_purchase", {"purchase": presentation(data)}))
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning-purchases/<int:mandate_id>/assign", type="http", auth="user", website=True, methods=["POST"]
    )
    def assign(self, mandate_id, **post):
        try:
            request.env["training.elearning.company.service"]._assign(mandate_id, int(post.get("beneficiary", "0")))
            return private(request.redirect("/my/learning-purchases/%s" % mandate_id))
        except (AccessError, MissingError):
            raise request.not_found() from None
        except (ValueError, ValidationError, LockError):
            return private(
                request.make_response(
                    "L’attribution ne peut pas être finalisée. Actualisez cette page ou contactez la coordination.",
                    status=400,
                )
            )


from odoo.addons.portal.controllers.portal import CustomerPortal  # noqa: E402


class CompanyPortalHome(CustomerPortal):
    def _prepare_portal_counter_values(self, counter):
        if counter == "learning_purchases_count":
            # The native counter may count only IDs whose live mandate has
            # already passed the same checks as the purchase page.
            purchases = request.env["training.elearning.company.service"]._list()
            return "training.elearning.sale.mandate", [("id", "in", [p["id"] for p in purchases])], "sudo"
        return super()._prepare_portal_counter_values(counter)


class PurchaseReportExport(http.Controller):
    @http.route(
        "/my/learning-purchases/<int:mandate_id>/summary.csv",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def summary_csv(self, mandate_id, **kw):
        import csv
        import io

        try:
            # Recheck the exact live mandate at download; no attachment token
            # or previously rendered page grants a durable download right.
            data = presentation(request.env["training.elearning.company.service"]._view(mandate_id))
        except (AccessError, MissingError):
            raise request.not_found() from None
        output = io.StringIO(newline="")
        writer = csv.writer(output)

        def safe(value):
            value = str(value) if value is not None and value is not False else ""
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value

        writer.writerow(
            [
                "Achat",
                "Date de l’export",
                "Fuseau",
                "Bénéficiaire",
                "Depuis",
                "Jusqu’au",
                "État",
                "Progression des cours financés (%)",
                "Achevé",
                "Date d’achèvement",
                "Bilan figé",
            ]
        )
        for row in data["rows"]:
            summary = row.get("summary", {})
            values = [
                data["reference"],
                format_datetime(request.env, fields.Datetime.now(), tz=request.env.user.tz or "UTC"),
                data["timezone"],
                row["beneficiary"],
                row["start"],
                row["end"],
                row["state"],
                summary.get("percentage", ""),
                "Oui" if summary.get("complete") else "Non",
                summary.get("completed_at") or "",
                "Oui" if summary.get("closed_at") else "Non",
            ]
            writer.writerow([safe(value) for value in values])
        return private(
            request.make_response(
                "\ufeff" + output.getvalue(),
                headers=[
                    ("Content-Type", "text/csv; charset=utf-8"),
                    ("Content-Disposition", 'attachment; filename="bilan-achat.csv"'),
                ],
            )
        )
