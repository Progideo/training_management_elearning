# pylint: disable=super-method-mismatch,method-required-super,context-overridden
"""Owned formative attempts and atomic native evidence projection, without TM."""

import hashlib
import json
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.addons.training_interactive.services.events import encode_report, validate_result


def encode(value, env):
    try:
        return encode_report(value)
    except ValueError as error:
        raise ValidationError(env._("Invalid or excessive formative report")) from error


class Attempt(models.Model):
    _name = "training.elearning.interactive.attempt"
    _description = "Autonomous Formative Interactive Attempt"
    _rec_name = "number"
    _order = "id desc"
    membership_id = fields.Many2one("slide.channel.partner", required=True, readonly=True, ondelete="restrict")
    slide_id = fields.Many2one("slide.slide", required=True, readonly=True, ondelete="restrict")
    company_id = fields.Many2one(related="membership_id.channel_id.learning_company_id", store=True)
    version_id = fields.Many2one("training.elearning.version", required=True, readonly=True, ondelete="restrict")
    actor_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    number = fields.Integer(required=True, readonly=True)
    request_key = fields.Char(required=True, readonly=True)
    revision = fields.Integer(readonly=True)
    state_json = fields.Text(default="{}", readonly=True, groups="base.group_system")
    result_json = fields.Text(default="{}", readonly=True, groups="base.group_system")
    score = fields.Float(readonly=True)
    maximum = fields.Float(readonly=True)
    completed = fields.Boolean(readonly=True)
    last_saved_at = fields.Datetime(readonly=True)
    _one_number = models.Constraint(
        "UNIQUE(membership_id,slide_id,number)", "This lesson attempt number already exists."
    )
    _one_request = models.Constraint("UNIQUE(request_key)", "This launch request already exists.")

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Use the owned formative launch service."))

    def write(self, values):
        raise AccessError(self.env._("Save through the checked interactive report service."))

    @api.ondelete(at_uninstall=False)
    def _keep_attempt(self):
        raise AccessError(self.env._("Keep formative attempt history."))

    @api.private
    def _scope(self, membership_id, slide_id, *, lock=False):
        member, slide, item = self.env["training.elearning.service"]._activity(membership_id, slide_id, lock=lock)
        if item["kind"] != "interactive":
            raise AccessError(self.env._("Choose an authorized interactive lesson."))
        version = self.env["training.elearning.version"].sudo().browse(item["version"])
        return member, slide, item, version

    @api.private
    def _authorize(self, *, lock=False):
        self.ensure_one()
        attempt = self.sudo().exists()
        if not attempt or attempt.actor_id != self.env.user:
            raise AccessError(self.env._("This formative attempt is unavailable."))
        member, slide, item, version = self._scope(attempt.membership_id.id, attempt.slide_id.id, lock=lock)
        if attempt.version_id != version:
            raise AccessError(self.env._("Keep the frozen lesson version of this attempt."))
        return member, slide, item, version

    @api.private
    def _start(self, membership_id, slide_id, request_key, *, new=False):
        if not isinstance(request_key, str) or not 16 <= len(request_key) <= 80:
            raise ValidationError(self.env._("Use a valid launch request identifier."))
        with self.env.cr.savepoint():
            member, slide, _item, version = self._scope(membership_id, slide_id, lock=True)
            existing = self.sudo().search([("request_key", "=", request_key)], limit=1)
            if existing:
                if existing.membership_id != member or existing.slide_id != slide or existing.actor_id != self.env.user:
                    raise ValidationError(self.env._("This launch request belongs to another context."))
                return existing.with_user(self.env.user)
            member._interactive_touch()
            latest = self.sudo().search(
                [("membership_id", "=", member.id), ("slide_id", "=", slide.id)], order="number desc", limit=1
            )
            if latest and not new:
                return latest.with_user(self.env.user)
            attempt = super(Attempt, self.sudo().with_context({})).create(
                {
                    "membership_id": member.id,
                    "slide_id": slide.id,
                    "version_id": version.id,
                    "actor_id": self.env.uid,
                    "number": latest.number + 1 if latest else 1,
                    "request_key": request_key,
                }
            )
            return attempt.with_user(self.env.user)

    @api.private
    def _snapshot(self):
        self._authorize()
        attempt = self.sudo()
        return {
            "attempt": attempt.id,
            "number": attempt.number,
            "revision": attempt.revision,
            "state": json.loads(attempt.state_json),
            "result": json.loads(attempt.result_json),
        }

    @api.private
    def _save(self, key, revision, payload):
        with self.env.cr.savepoint():
            member, slide, item, version = self._authorize(lock=True)
            self.lock_for_update()
            self.invalidate_recordset()
            attempt = self.sudo()
            if (
                not isinstance(key, str)
                or not 1 <= len(key) <= 80
                or type(revision) is not int
                or revision < 1
                or not isinstance(payload, dict)
                or not payload
                or set(payload) - {"state", "result"}
            ):
                raise ValidationError(self.env._("Use a valid formative event schema."))
            encoded = encode({"revision": revision, "payload": payload}, self.env)
            digest = hashlib.sha256(encoded.encode()).hexdigest()
            events = self.env["training.elearning.interactive.event"].sudo()
            previous = events.search([("attempt_id", "=", attempt.id), ("key", "=", key)], limit=1)
            if previous:
                if previous.sha256 != digest:
                    raise ValidationError(self.env._("This event identifier has a different payload."))
                return json.loads(previous.receipt_json)
            latest = self.sudo().search(
                [("membership_id", "=", member.id), ("slide_id", "=", slide.id)], order="number desc", limit=1
            )
            if latest != attempt or revision != attempt.revision + 1:
                raise ValidationError(self.env._("A newer attempt or revision exists; reload before continuing."))
            values = {"revision": revision, "last_saved_at": fields.Datetime.now()}
            if "state" in payload:
                if not isinstance(payload["state"], dict):
                    raise ValidationError(self.env._("Use an object for the private resume state."))
                values["state_json"] = encode(payload["state"], self.env)
            result = payload.get("result")
            if "result" in payload:
                try:
                    validate_result(result, version.resource_id.format)
                except ValueError as error:
                    raise ValidationError(
                        self.env._("The formative result is invalid for this package format.")
                    ) from error
                values.update(
                    score=result["score"],
                    maximum=result["maximum"],
                    completed=result["completed"],
                    result_json=encode(result, self.env),
                )
            super(Attempt, attempt).write(values)
            receipt = {"ok": True, "attempt": attempt.id, "revision": revision}
            events._append(
                {
                    "attempt_id": attempt.id,
                    "key": key,
                    "sha256": digest,
                    "payload_json": encoded,
                    "receipt_json": encode(receipt, self.env),
                }
            )
            if (
                result
                and result["completed"]
                and (
                    item["rule"] == "completed"
                    or (result["maximum"] > 0 and 100 * result["score"] / result["maximum"] >= item["threshold"])
                )
            ):
                # The first acquired native leaf remains true after later low
                # performances. Event, state and native projection commit together.
                self.env["slide.slide.partner"]._learning_project(member, slide.id, True)
                member._learning_sync_progress()
            return receipt


class Event(models.Model):
    _name = "training.elearning.interactive.event"
    _description = "Immutable Autonomous Formative Event"
    attempt_id = fields.Many2one(
        "training.elearning.interactive.attempt", required=True, readonly=True, ondelete="restrict"
    )
    company_id = fields.Many2one(related="attempt_id.company_id", store=True)
    key = fields.Char(required=True, readonly=True)
    sha256 = fields.Char(required=True, readonly=True)
    payload_json = fields.Text(required=True, readonly=True, groups="base.group_system")
    receipt_json = fields.Text(required=True, readonly=True, groups="base.group_system")
    _one_event = models.Constraint("UNIQUE(attempt_id,key)", "This formative event already exists.")

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Use the atomic formative save service."))

    @api.private
    def _append(self, values):
        return super(Event, self.sudo().with_context({})).create(values)

    def write(self, values):
        raise AccessError(self.env._("Keep immutable formative events."))

    @api.ondelete(at_uninstall=False)
    def _keep_event(self):
        raise AccessError(self.env._("Keep original formative event history."))
