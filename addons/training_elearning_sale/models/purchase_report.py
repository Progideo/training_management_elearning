# pylint: disable=super-method-mismatch,method-required-super,context-overridden
"""Purchase-period summaries derive native evidence; they never drive learner progression."""

from datetime import timedelta
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

PEDAGOGY = "training_elearning.group_elearning_pedagogy_manager"


class CourseReport(models.Model):
    _name = "training.elearning.sale.course.report"
    _description = "Purchase Scoped Course Summary"
    _rec_name = "allocation_id"
    allocation_id = fields.Many2one(
        "training.elearning.sale.allocation", required=True, readonly=True, ondelete="restrict"
    )
    company_id = fields.Many2one(related="allocation_id.company_id", store=True)
    beneficiary_id = fields.Many2one(related="allocation_id.partner_id")
    course_id = fields.Many2one(related="membership_id.channel_id")
    percentage = fields.Float(compute="_compute_summary", string="Progression (%)")
    complete = fields.Boolean(compute="_compute_summary")
    completed_at = fields.Datetime(compute="_compute_summary")
    waiting_correction = fields.Boolean(compute="_compute_summary")
    prerequisite_blocked = fields.Boolean(compute="_compute_summary")

    @api.depends("snapshot", "closed_at", "ends_at")
    def _compute_summary(self):
        for report in self:
            result = report._evaluate()
            report.percentage = result["percentage"]
            report.complete = result["complete"]
            report.completed_at = fields.Datetime.to_datetime(result["completed_at"])
            report.waiting_correction = result["waiting_correction"]
            report.prerequisite_blocked = result["prerequisite_blocked"]

    membership_id = fields.Many2one("slide.channel.partner", required=True, readonly=True, ondelete="restrict")
    starts_at = fields.Datetime(required=True, readonly=True)
    ends_at = fields.Datetime(required=True, readonly=True)
    baseline = fields.Json(readonly=True, groups=PEDAGOGY)
    prerequisite_baseline = fields.Boolean(readonly=True)
    closed_at = fields.Datetime(readonly=True)
    snapshot = fields.Json(readonly=True)
    snapshot_history = fields.Json(readonly=True, groups=PEDAGOGY)
    _one_course = models.Constraint(
        "UNIQUE(allocation_id, membership_id)", "This purchase already has this course summary."
    )

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Course summaries originate in effective purchase grants."))

    def write(self, values):
        raise AccessError(self.env._("Keep purchase summary evidence and closure history."))

    @api.ondelete(at_uninstall=False)
    def _keep_report(self):
        raise AccessError(self.env._("Keep purchase summaries and their history."))

    @api.private
    def _store(self, values):
        return super(CourseReport, self.sudo()).write(values)

    @api.private
    def _ensure(self, allocation, member, start, end):
        allocation, member = allocation.sudo(), member.sudo()
        if (
            not allocation.activated_at
            or not member.learning_started_at
            or allocation.partner_id != member.partner_id
            or allocation.company_id != member.channel_id.learning_company_id
            or not start
            or not end
            or end <= start
        ):
            raise ValidationError(self.env._("Use the effective native grant of this purchase and beneficiary."))
        allocation.lock_for_update()
        old = self.sudo().search([("allocation_id", "=", allocation.id), ("membership_id", "=", member.id)], limit=1)
        if old:
            return old
        # A deliberate new grant captures pre-existing acquired lessons. An
        # upgrade never invents historical completion dates for legacy rows.
        acquired = (
            self.env["slide.slide.partner"]
            .sudo()
            .search(
                [
                    ("partner_id", "=", member.partner_id.id),
                    ("slide_id.channel_id", "=", member.channel_id.id),
                    ("completed", "=", True),
                ]
            )
        )
        return super(CourseReport, self.sudo().with_context({})).create(
            {
                "allocation_id": allocation.id,
                "membership_id": member.id,
                "starts_at": start,
                "ends_at": end,
                "baseline": acquired.slide_id.ids,
                "prerequisite_baseline": self.env["training.elearning.service"]._course_prerequisites(member),
            }
        )

    @api.private
    def _human_status(self, slide_id, now):
        """Only receivable work within this purchase, plus its one late revision."""
        self.ensure_one()
        rows = (
            self.env["training.elearning.submission"]
            .sudo()
            .search(
                [
                    ("membership_id", "=", self.membership_id.id),
                    ("slide_id", "=", slide_id),
                ],
                order="received_at,id",
            )
        )
        eligible = self.env["training.elearning.submission"]
        late = False
        revision_days = self.allocation_id.line_id.learning_revision_days
        for row in rows:
            if row.received_at < self.ends_at:
                eligible |= row
                continue
            parent = row.revision_parent_id
            notice = parent.delivery_notice_id
            if (
                not late
                and parent
                and parent.outcome == "revision"
                and parent.revision_eligible
                and parent.submission_id in eligible
                and parent.submission_id.received_at < self.ends_at
                and notice.state == "sent"
                and not notice.failed
                and notice.sent_at
                and row.received_at < notice.sent_at + timedelta(days=revision_days)
            ):
                eligible |= row
                late = True
        reviews = eligible.review_id
        complete = reviews.filtered(lambda review: review.outcome == "validated")
        final = self.ends_at
        waiting = False
        for review in reviews:
            review._sync_delivery()
            notice = review.delivery_notice_id
            if notice.state != "sent" or notice.failed or not notice.sent_at:
                waiting = True
                continue
            final = max(final, review.published_at, notice.sent_at)
            if (
                review.outcome == "revision"
                and review.revision_eligible
                and review.submission_id.received_at < self.ends_at
                and not eligible.filtered(lambda row: row.revision_parent_id == review)
            ):
                until = notice.sent_at + timedelta(days=revision_days)
                final = max(final, until)
                waiting = waiting or now < until
        queue = rows.review_queue_id[:1]
        waiting_correction = bool(queue and queue.state == "pending" and queue.submission_id in eligible)
        waiting = waiting or waiting_correction
        # A replaced candidate outside this period is not attributed back to
        # this purchase. No grades, files or review text enter this projection.
        return {
            "complete": bool(complete),
            "completed_at": min(complete.mapped("published_at")) if complete else False,
            "waiting": waiting,
            "waiting_correction": waiting_correction,
            "final": final,
        }

    @api.private
    def _evaluate(self):
        self.ensure_one()
        report = self.sudo()
        now = fields.Datetime.now()
        member = report.membership_id
        member.lock_for_update()
        report.lock_for_update()
        report.invalidate_recordset()
        items = member._learning_plan()["slides"]
        required = [item for item in items if item["required"]]
        rows = (
            self.env["slide.slide.partner"]
            .sudo()
            .search(
                [
                    ("partner_id", "=", member.partner_id.id),
                    ("slide_id", "in", [item["id"] for item in items]),
                ]
            )
        )
        evidence = {row.slide_id.id: row for row in rows}
        dates, satisfied, waiting = [], 0, False
        waiting_correction = False
        final = report.ends_at
        for item in items:
            row = evidence.get(item["id"])
            stamp = row.learning_completed_at if row else False
            completed = item["id"] in (report.baseline or []) or bool(stamp and stamp < report.ends_at)
            completed_at = max(report.starts_at, stamp) if stamp and completed else report.starts_at
            if item.get("kind") == "task":
                task = self.env["training.elearning.practical"].sudo().browse(item.get("task")).exists()
                if task.criterion == "human":
                    human = report._human_status(item["id"], now)
                    completed = completed or human["complete"]
                    if human["complete"]:
                        completed_at = max(report.starts_at, human["completed_at"])
                    waiting = waiting or human["waiting"]
                    waiting_correction = waiting_correction or human["waiting_correction"]
                    final = max(final, human["final"])
            if completed and item["required"]:
                satisfied += 1
                dates.append(completed_at)
        complete = satisfied == len(required)
        summary = {
            "required": len(required),
            "satisfied": satisfied,
            "percentage": round(100 * satisfied / len(required)) if required else 100,
            "complete": complete,
            "completed_at": fields.Datetime.to_string(max(dates or [report.starts_at])) if complete else False,
            "waiting_correction": waiting_correction,
            "prerequisite_blocked": not (
                report.prerequisite_baseline
                or all(
                    previous.completion_date and previous.completion_date < report.ends_at
                    for course in member._learning_plan().get("courses", [])
                    for previous in [
                        self.env["slide.channel.partner"]
                        .sudo()
                        .search(
                            [
                                ("channel_id", "=", course),
                                ("partner_id", "=", member.partner_id.id),
                            ],
                            limit=1,
                        )
                    ]
                )
            ),
        }
        if report.closed_at and (waiting or final > report.closed_at):
            history = list(report.snapshot_history or [])
            history.append({"at": fields.Datetime.to_string(report.closed_at), "summary": report.snapshot})
            report._store({"closed_at": False, "snapshot": False, "snapshot_history": history})
        if now >= report.ends_at and not waiting and now >= final:
            if not report.closed_at:
                report._store({"closed_at": final, "snapshot": summary})
            return {**report.snapshot, "closed_at": report.closed_at, "pending": False}
        return {**summary, "closed_at": False, "pending": waiting}

    @api.private
    def _cron_close_reports(self):
        params = self.env["ir.config_parameter"].sudo()
        cursor = int(params.get_str("training_elearning_sale.report_scan_cursor", "0"))
        reports = self.sudo().search(
            [
                ("ends_at", "<=", fields.Datetime.now()),
                ("id", ">", cursor),
            ],
            order="id",
            limit=500,
        )
        for report in reports:
            with self.env.cr.savepoint():
                report._evaluate()
        # Revisit closed reports too: a later native bounce can require a new
        # closure, while advancing the cursor prevents starving newer grants.
        params.set_str("training_elearning_sale.report_scan_cursor", str(reports[-1].id if len(reports) == 500 else 0))


class Allocation(models.Model):
    _inherit = "training.elearning.sale.allocation"
    report_course_ids = fields.One2many("training.elearning.sale.course.report", "allocation_id", readonly=True)

    def action_learning_activate(self):
        result = super().action_learning_activate()
        for seat in self.filtered("membership_id"):
            self.env["training.elearning.sale.course.report"]._ensure(
                seat, seat.membership_id, seat.access_started_at, seat.access_ends_at
            )
        return result

    @api.private
    def _purchase_summary(self):
        self.ensure_one()
        reports = self.sudo().report_course_ids
        if not reports:
            return {"available": False}
        results = [report._evaluate() for report in reports]
        total = sum(row["required"] for row in results)
        satisfied = sum(row["satisfied"] for row in results)
        complete = all(row["complete"] for row in results)
        completion_dates = [row["completed_at"] for row in results if row["completed_at"]]
        if self.path_activation_id:
            context = self.sudo().path_activation_id
            required = {
                item["course"]
                for item in context.registration_id.composition
                if item["required"] and item["course"] in context.plan["included"]
            }
            total = len(required)
            satisfied = sum(
                row["complete"]
                for report, row in zip(reports, results)
                if report.membership_id.channel_id.id in required
            )
            complete = bool(total) and satisfied == total
            completion_dates = [
                row["completed_at"]
                for report, row in zip(reports, results)
                if report.membership_id.channel_id.id in required and row["completed_at"]
            ]

        closures = [row["closed_at"] for row in results if row["closed_at"]]
        return {
            "available": True,
            "percentage": round(100 * satisfied / total) if total else (0 if self.path_activation_id else 100),
            "complete": complete,
            "completed_at": max(completion_dates) if complete and completion_dates else False,
            "waiting_correction": any(row["waiting_correction"] for row in results),
            "prerequisite_blocked": any(row["prerequisite_blocked"] for row in results),
            "closed_at": max(closures)
            if len(closures) == len(reports)
            and (not self.path_activation_id or fields.Datetime.now() >= self._path_period_end())
            else False,
            "pending": any(row["pending"] for row in results),
        }


class PathItem(models.Model):
    _inherit = "training.elearning.path.item"

    @api.private
    def _start(self):
        result = super()._start()
        if result and self.activation_id.sale_allocation_id:
            self.env["training.elearning.sale.course.report"]._ensure(
                self.activation_id.sale_allocation_id, self.membership_id, self.access_started_at, self.access_ends_at
            )
        return result


class CompanyPortal(models.AbstractModel):
    _inherit = "training.elearning.company.service"

    @api.private
    def _seat_row(self, seat, now):
        row = super()._seat_row(seat, now)
        return {**row, "summary": seat._purchase_summary()}

    @api.private
    def _ends_at(self, mandate):
        line = mandate.sudo().line_id
        periods = (
            [line.learning_assign_until]
            if (line.learning_assign_until and len(line.learning_allocation_ids) < line.product_uom_qty)
            else []
        )
        for seat in line.learning_allocation_ids.filtered("activated_at"):
            summary = seat._purchase_summary()
            if summary.get("pending"):
                return mandate.valid_until
            end = seat._path_period_end() if seat.path_activation_id else seat.access_ends_at
            periods.append(max(end, summary["closed_at"]) if summary.get("closed_at") else end)
        if not periods:
            return super()._ends_at(mandate)
        return min(mandate.valid_until, max(periods) + relativedelta(months=line.learning_report_months))


class ReviewQueue(models.Model):
    _inherit = "training.elearning.review.queue"

    @api.private
    def _accept(self, submission, item):
        queue = super()._accept(submission, item)
        contracts = (
            self.env["training.elearning.sale.course.report"]
            .sudo()
            .search(
                [
                    ("membership_id", "=", submission.membership_id.id),
                    ("starts_at", "<=", submission.received_at),
                    ("ends_at", ">", submission.received_at),
                ]
            )
        )
        calendar = self.env["resource.calendar"].sudo().browse(item.get("review_calendar"))
        deadlines = [queue.due_at]
        for contract in contracts:
            deadlines.append(
                calendar._learning_deadline(
                    queue.first_received_at, contract.allocation_id.line_id.learning_review_days
                )
            )
        queue._store({"due_at": min(deadlines)})
        return queue


class ReviewNotice(models.Model):
    _inherit = "training.elearning.review.notice"

    @api.private
    def _sent(self, at):
        result = super()._sent(at)
        if self.kind != "feedback" or not self.review_id.revision_eligible or self.queue_id.review_id != self.review_id:
            return result
        submission = self.review_id.submission_id
        contracts = (
            self.env["training.elearning.sale.course.report"]
            .sudo()
            .search(
                [
                    ("membership_id", "=", submission.membership_id.id),
                    ("starts_at", "<=", submission.received_at),
                    ("ends_at", ">", submission.received_at),
                ]
            )
        )
        windows = [self.queue_id.revision_until]
        windows += [
            at + timedelta(days=contract.allocation_id.line_id.learning_revision_days) for contract in contracts
        ]
        if any(windows):
            self.queue_id._store({"revision_until": max(window for window in windows if window)})
        return result
