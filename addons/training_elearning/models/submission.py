"""A private receivable deposit is detailed proof, projected into native progression."""

import re
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .submission_files import InvalidSubmission, validate_files

PEDAGOGY = "training_elearning.group_elearning_pedagogy_manager"


class Submission(models.Model):
    _name = "training.elearning.submission"
    _description = "Practical Submission Metadata"
    _rec_name = "received_at"
    membership_id = fields.Many2one(
        "slide.channel.partner", required=True, readonly=True, ondelete="restrict", index=True
    )
    slide_id = fields.Many2one("slide.slide", required=True, readonly=True, ondelete="restrict")
    practical_id = fields.Many2one("training.elearning.practical", required=True, readonly=True, ondelete="restrict")
    company_id = fields.Many2one(related="membership_id.channel_id.learning_company_id")
    received_at = fields.Datetime(required=True, readonly=True)
    request_key = fields.Char(required=True, readonly=True)
    state = fields.Selection([("received", "Receivable Deposit")], default="received", readonly=True)
    payload_id = fields.Many2one("training.elearning.submission.payload", readonly=True, ondelete="restrict")
    _one_request = models.Constraint(
        "UNIQUE(membership_id, slide_id, request_key)", "This submission request is already recorded."
    )

    @api.model_create_multi
    def create(self, vals_list):  # pylint: disable=method-required-super
        raise AccessError(self.env._("Use the checked private practical submission service."))

    def write(self, values):  # pylint: disable=method-required-super
        raise AccessError(self.env._("Keep the submission identity and receivable timestamp."))

    @api.private
    def _create_receivable(self, values):
        return super(Submission, self.sudo().with_context({})).create(values)  # pylint: disable=super-method-mismatch,context-overridden

    @api.private
    def _store(self, values):
        return super(Submission, self.sudo()).write(values)  # pylint: disable=super-method-mismatch

    @api.ondelete(at_uninstall=False)
    def _keep_submission(self):
        raise AccessError(self.env._("Keep practical submissions and their history."))

    def action_private_payload(self):
        self.ensure_one()
        self.check_access("read")
        if not self.exists() or not self.payload_id:
            raise AccessError(self.env._("This private submission is unavailable."))
        self.payload_id._authorize_staff()
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.submission.payload",
            "res_id": self.payload_id.id,
            "view_mode": "form",
        }


class Payload(models.Model):
    _name = "training.elearning.submission.payload"
    _description = "Private Practical Submission Files"
    _rec_name = "submission_id"
    submission_id = fields.Many2one("training.elearning.submission", required=True, readonly=True, ondelete="restrict")
    company_id = fields.Many2one(related="submission_id.company_id")
    file_ids = fields.Many2many(
        "ir.attachment", "learning_submission_file_rel", "payload_id", "attachment_id", readonly=True
    )
    file_evidence = fields.Json(readonly=True)
    _one_payload = models.Constraint("UNIQUE(submission_id)", "This submission already has its private files.")

    @api.private
    def _authorize_staff(self):
        if not self.env.user.active or not self.env.user.has_group(PEDAGOGY):
            raise AccessError(self.env._("Pedagogical coordination permission is required for practical files."))
        self.check_access("read")
        if any(
            item.company_id not in self.env.companies or item.company_id not in self.env.user.company_ids
            for item in self
        ):
            raise AccessError(self.env._("Use practical files in your active companies."))

    @api.model_create_multi
    def create(self, vals_list):  # pylint: disable=method-required-super
        raise AccessError(self.env._("Practical files are created by checked receivable deposits."))

    def write(self, values):  # pylint: disable=method-required-super
        raise AccessError(self.env._("Keep the private submission bytes and file evidence."))

    @api.private
    def _create_files(self, submission, validated):
        payload = super(Payload, self.sudo().with_context({})).create({"submission_id": submission.id})  # pylint: disable=super-method-mismatch,context-overridden
        files = self.env["ir.attachment"]
        evidence = {}
        for item in validated:
            file = self.env["ir.attachment"]._learning_submission_file(payload, item)
            files |= file
            evidence[str(file.id)] = {key: item[key] for key in ("name", "mimetype", "size", "sha256")}
        super(Payload, payload).write({"file_ids": [(6, 0, files.ids)], "file_evidence": evidence})  # pylint: disable=super-method-mismatch
        return payload

    @api.ondelete(at_uninstall=False)
    def _keep_payload(self):
        raise AccessError(self.env._("Keep the submitted files and their evidence."))


class PracticalService(models.AbstractModel):
    _name = "training.elearning.practical.service"
    _description = "Private Practical Learner Operations"

    @api.private
    def _context(self, membership_id, slide_id, *, history=False, lock=False):
        service = self.env["training.elearning.service"]
        member = service._membership(membership_id, history=history, lock=lock)
        if history:
            item = next((item for item in member._learning_plan()["slides"] if item["id"] == slide_id), None)
            slide = self.env["slide.slide"].sudo().browse(slide_id).exists()
        else:
            member, slide, item = service._activity(membership_id, slide_id)
        if not item or item["kind"] != "task" or not slide or slide.channel_id != member.channel_id:
            raise AccessError(self.env._("This private practical context is unavailable."))
        task = self.env["training.elearning.practical"].sudo().browse(item["task"]).exists()
        if (
            not task
            or task.state != "published"
            or task.training_course_id != member.channel_id.training_course_id
            or task.company_id != member.channel_id.learning_company_id
        ):
            raise AccessError(self.env._("This private practical version is unavailable."))
        return member, slide, task

    @api.private
    def _declare(self, membership_id, slide_id):
        member, slide, task = self._context(membership_id, slide_id, lock=True)
        if task.criterion != "self":
            raise AccessError(self.env._("This practical requires a receivable deposit, not a declaration."))
        self.env["slide.slide.partner"]._learning_project(member, slide.id, True)
        member._learning_sync_progress()
        return True

    @api.private
    def _deposit(self, membership_id, slide_id, files, request_key):
        if not isinstance(request_key, str) or not re.fullmatch(r"[0-9a-f-]{36}", request_key):
            raise ValidationError(self.env._("Reload the practical form before submitting."))
        member, slide, task = self._context(membership_id, slide_id, history=True, lock=True)
        submissions = self.env["training.elearning.submission"]
        previous = submissions.sudo().search(
            [("membership_id", "=", member.id), ("slide_id", "=", slide.id), ("request_key", "=", request_key)], limit=1
        )
        if previous:
            return previous
        self._context(membership_id, slide_id)
        if task.criterion != "deposit":
            raise AccessError(self.env._("Use this practical's own completion criterion."))
        received = fields.Datetime.now()
        try:
            validated = validate_files(files, task._policy())
        except InvalidSubmission as error:
            raise ValidationError(self._file_error(str(error), task)) from error
        with self.env.cr.savepoint():
            submission = submissions._create_receivable(
                {
                    "membership_id": member.id,
                    "slide_id": slide.id,
                    "practical_id": task.id,
                    "received_at": received,
                    "request_key": request_key,
                }
            )
            payload = self.env["training.elearning.submission.payload"]._create_files(submission, validated)
            submission._store({"payload_id": payload.id})
            self.env["slide.slide.partner"]._learning_project(member, slide.id, True)
            member._learning_sync_progress()
        return submission

    @api.private
    def _file_error(self, cause, task):
        messages = {
            "file_count_limit": self.env._(
                "Ajoutez au moins un fichier, dans la limite de %(maximum)s fichiers.", maximum=task.max_files
            ),
            "single_file_size_limit": self.env._(
                "Un fichier est vide ou dépasse la limite de %(maximum)s Mo.", maximum=task.file_mib
            ),
            "total_size_limit": self.env._(
                "Le rendu dépasse la limite totale de %(maximum)s Mo.", maximum=task.total_mib
            ),
            "invalid_filename": self.env._(
                "Utilisez des noms de fichiers simples, sans chemin ni caractères de contrôle."
            ),
            "file_type_not_allowed": self.env._(
                "Un format n’est pas autorisé pour ce TP. Consultez la liste annoncée avant le dépôt."
            ),
            "macros_or_embedded_executable": self.env._(
                "Les macros et objets exécutables incorporés ne sont pas admis."
            ),
            "active_office_relationship": self.env._(
                "Le document contient une liaison externe automatique ou un objet actif non admis."
            ),
            "office_expansion_limit": self.env._(
                "Le document bureautique dépasse les limites de décompression de sécurité."
            ),
            "encrypted_or_empty_pdf": self.env._("Le PDF est chiffré ou ne contient aucune page exploitable."),
        }
        return messages.get(
            cause,
            self.env._("Le fichier ne correspond pas à un format valide autorisé. Aucun rendu n’a été enregistré."),
        )

    @api.private
    def _history(self, submission_id):
        row = self.env["training.elearning.submission"].sudo().browse(submission_id).exists()
        if not row:
            raise AccessError(self.env._("This private practical submission is unavailable."))
        _member, _slide, task = self._context(row.membership_id.id, row.slide_id.id, history=True)
        if row.practical_id != task or not row.payload_id or row.payload_id.submission_id != row:
            raise AccessError(self.env._("This private practical submission is unavailable."))
        return row
