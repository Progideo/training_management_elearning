"""Run only in the disposable fictional database created by test-resources.py."""
import hashlib
import io
import json
import os
import zipfile
from datetime import timedelta
from pathlib import Path
from psycopg2.errors import SerializationFailure
from odoo import api, fields
from odoo.exceptions import ValidationError
from odoo.tests import new_test_user
from odoo.tools import BinaryBytes

assert env.cr.dbname == "resources_fictional", "This probe is restricted to a disposable fictional database"
phase = os.environ["RESOURCE_PROBE_PHASE"]
checkpoint = Path("/var/lib/odoo/resource-checkpoint.json")


def make_course(manager, catalog, name):
    course = env["slide.channel"].with_user(manager).create({"name": name, "training_course_id": catalog.id})
    slide = env["slide.slide"].with_user(manager).create({
        "name": "Fictional resource activity", "channel_id": course.id, "slide_category": "article",
        "html_content": "<p>Fictional preservation content</p>", "is_published": True})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("exercise.txt", "Fictional preservation bytes")
    resource = env["slide.slide.resource"].with_user(manager).create({
        "slide_id": slide.id, "resource_type": "file", "name": "Fictional exercises",
        "file_name": "exercises.zip", "data": BinaryBytes(output.getvalue())})
    course.action_learning_publish()
    return course, slide, resource


if phase == "prepare":
    ctx = dict(env.context, no_reset_password=True)
    manager = new_test_user(env(context=ctx), login="fictional_preserved_resource_manager",
                            groups="training_elearning.group_elearning_manager")
    owner = new_test_user(env(context=ctx), login="fictional_preserved_resource_owner", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional preservation catalogue"})
    course, slide, resource = make_course(manager, catalog, "Fictional preserved edition")
    member = env["slide.channel.partner"].with_user(manager).create({
        "channel_id": course.id, "partner_id": owner.partner_id.id})
    member.action_learning_activate(fields.Datetime.now() + timedelta(days=365), owner.id, "Fictional preservation")
    original = dict(member=member.id, resource=resource.id, slide=slide.id, owner=owner.id,
                    manager=manager.id, plan=member.learning_plan,
                    starts=fields.Datetime.to_string(member.learning_started_at),
                    ends=fields.Datetime.to_string(member.learning_ends_at), completion=member.completion)
    env.cr.commit()
    checkpoint.write_text(json.dumps(original, sort_keys=True))
    print("RESOURCE_PROBE=prepared")
elif phase == "preserved":
    expected = json.loads(checkpoint.read_text())
    member = env["slide.channel.partner"].browse(expected["member"])
    assert member.learning_plan == expected["plan"]
    assert fields.Datetime.to_string(member.learning_started_at) == expected["starts"]
    assert fields.Datetime.to_string(member.learning_ends_at) == expected["ends"]
    assert member.completion == expected["completion"] == 0
    resource, snapshot = env["training.elearning.resource.service"].with_user(expected["owner"])._context(
        member.id, expected["slide"], expected["resource"])
    assert hashlib.sha256(resource.data.content).hexdigest() == snapshot["sha256"]
    print("RESOURCE_PROBE=preserved")
elif phase == "concurrency":
    expected = json.loads(checkpoint.read_text())
    manager = env["res.users"].browse(expected["manager"])
    owner = env["res.users"].browse(expected["owner"])
    catalog = env["training.course"].create({"name": "Fictional concurrent resource catalogue"})
    for editor_first in (True, False):
        course, slide, resource = make_course(manager, catalog, "Fictional concurrent edition")
        member = env["slide.channel.partner"].with_user(manager).create({
            "channel_id": course.id, "partner_id": owner.partner_id.id})
        env.cr.commit()
        # Two real PostgreSQL Repeatable Read snapshots; no mocks or context bypass.
        with env.registry.cursor() as stale_cr, env.registry.cursor() as writer_cr:
            stale = api.Environment(stale_cr, manager.id, {})
            writer = api.Environment(writer_cr, manager.id, {})
            stale["slide.channel"].browse(course.id).read(["name"])
            if editor_first:
                writer["slide.slide.resource"].browse(resource.id).write({"name": "Fictional edited exercises"})
                writer_cr.commit()
                operation = lambda: stale["slide.channel.partner"].browse(member.id).action_learning_activate(
                    fields.Datetime.now() + timedelta(days=365), owner.id, "Fictional concurrent activation")
            else:
                writer["slide.channel.partner"].browse(member.id).action_learning_activate(
                    fields.Datetime.now() + timedelta(days=365), owner.id, "Fictional concurrent activation")
                writer_cr.commit()
                operation = lambda: stale["slide.slide.resource"].browse(resource.id).write({"name": "Late replacement"})
            try:
                operation()
            except SerializationFailure:
                stale_cr.rollback()
            else:
                raise AssertionError("A stale resource/activation transaction must retry")
        with env.registry.cursor() as retry_cr:
            retry = api.Environment(retry_cr, manager.id, {})
            if editor_first:
                retried_member = retry["slide.channel.partner"].browse(member.id)
                retried_member.action_learning_activate(fields.Datetime.now() + timedelta(days=365), owner.id,
                                                        "Fictional retried activation")
                assert retried_member.learning_plan["slides"][0]["resources"][0]["name"] == "Fictional edited exercises"
                retry_cr.commit()
            else:
                try:
                    retry["slide.slide.resource"].browse(resource.id).write({"name": "Late replacement"})
                except ValidationError:
                    retry_cr.rollback()
                else:
                    raise AssertionError("A fresh retry must refuse the now-frozen resource")
    print("RESOURCE_PROBE=concurrency-passed")
else:
    raise AssertionError("Unknown probe phase")
