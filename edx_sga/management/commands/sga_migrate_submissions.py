"""
Django command which migrates existing SGA submissions for a course from all
old SGA implementation before v0.4.0 to newer version that uses the
'submissions' application.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from lms.djangoapps.courseware.courses import get_course_by_id
from lms.djangoapps.courseware.models import StudentModule
from opaque_keys.edx.keys import CourseKey
from common.djangoapps.student.models import anonymous_id_for_user
from submissions import api as submissions_api
from xmodule.modulestore.django import modulestore


class Command(BaseCommand):
    """
    Migrates existing SGA submissions for a course from old SGA implementation
    to newer version that uses the 'submissions' application.
    """

    args = "<course_id>"
    help = __doc__

    def handle(self, *args, **__options):
        """
        Migrates existing SGA submissions.
        """
        if not args:
            raise CommandError("Please specify the course id.")
        if len(args) > 1:
            raise CommandError("Too many arguments.")
        course_id = args[0]
        course_key = CourseKey.from_string(course_id)
        course = get_course_by_id(course_key)

        student_modules = StudentModule.objects.filter(course_id=course.id).filter(
            module_state_key__contains="edx_sga"
        )

        blocks = {}
        for student_module in student_modules:
            block_id = student_module.module_state_key
            if block_id.block_type != "edx_sga":
                continue
            block = blocks.get(block_id)
            if not block:
                blocks[block_id] = block = modulestore().get_item(block_id)
            state = json.loads(student_module.state)
            sha1 = state.get("uploaded_sha1")
            if not sha1:
                continue
            student = student_module.student
            submission_id = block.student_submission_id(
                anonymous_id_for_user(student, course.id)
            )
            answer = {
                "sha1": sha1,
                "filename": state.get("uploaded_filename"),
                "mimetype": state.get("uploaded_mimetype"),
            }
            submission = submissions_api.create_submission(submission_id, answer)
            score = state.get("score")  # float
            if score:
                submissions_api.set_score(
                    submission["uuid"], int(score), block.max_score()
                )
