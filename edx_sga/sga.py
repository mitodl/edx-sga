"""
This block defines a Staff Graded Assignment.  Students are shown a rubric
and invited to upload a file which is then graded by staff.
"""
import datetime
import hashlib
import json
import logging
import mimetypes
import os
import pkg_resources
import pytz

from functools import partial

from courseware.models import StudentModule

from django.core.exceptions import PermissionDenied
from django.core.files import File
from django.core.files.storage import default_storage
from django.template import Context, Template

from student.models import user_by_anonymous_id
from submissions import api as submissions_api
from submissions.models import StudentItem as SubmissionsStudent

from webob.response import Response

from xblock.core import XBlock
from xblock.exceptions import JsonHandlerError
from xblock.fields import DateTime, Scope, String, Float, Integer
from xblock.fragment import Fragment

from xmodule.util.duedate import get_extended_due_date


log = logging.getLogger(__name__)


def reify(meth):
    """
    Property which caches value so it is only computed once.
    """
    def getter(inst):
        value = meth(inst)
        inst.__dict__[meth.__name__] = value
        return value
    return property(getter)


class StaffGradedAssignmentXBlock(XBlock):
    """
    This block defines a Staff Graded Assignment.  Students are shown a rubric
    and invited to upload a file which is then graded by staff.
    """
    has_score = True
    icon_class = 'problem'

    display_name = String(
        default='Staff Graded Assignment', scope=Scope.settings,
        help="This name appears in the horizontal navigation at the top of "
             "the page."
    )

    weight = Float(
        display_name="Problem Weight",
        help=("Defines the number of points each problem is worth. "
              "If the value is not set, the problem is worth the sum of the "
              "option point values."),
        values={"min": 0, "step": .1},
        scope=Scope.settings
    )

    points = Integer(
        display_name="Maximum score",
        help=("Maximum grade score given to assignment by staff."),
        default=100,
        scope=Scope.settings
    )

    staff_score = Integer(
        display_name="Score assigned by non-instructor staff",
        help=("Score will need to be approved by instructor before being "
              "published."),
        default=None,
        scope=Scope.settings
    )

    comment = String(
        display_name="Instructor comment",
        default='',
        scope=Scope.user_state,
        help="Feedback given to student by instructor."
    )

    annotated_sha1 = String(
        display_name="Annotated SHA1",
        scope=Scope.user_state,
        default=None,
        help=("sha1 of the annotated file uploaded by the instructor for "
              "this assignment.")
    )

    annotated_filename = String(
        display_name="Annotated file name",
        scope=Scope.user_state,
        default=None,
        help="The name of the annotated file uploaded for this assignment."
    )

    annotated_mimetype = String(
        display_name="Mime type of annotated file",
        scope=Scope.user_state,
        default=None,
        help="The mimetype of the annotated file uploaded for this assignment."
    )

    annotated_timestamp = DateTime(
        display_name="Timestamp",
        scope=Scope.user_state,
        default=None,
        help="When the annotated file was uploaded")

    def max_score(self):
        return self.points

    @reify
    def block_id(self):
        # cargo culted gibberish
        return self.scope_ids.usage_id

    def student_submission_id(self, id=None):
        """
        Returns dict required by the submissions app for creating and
        retrieving submissions for a particular student.
        """
        if id is None:
            id = self.xmodule_runtime.anonymous_student_id
            assert id != 'MOCK', "Forgot to call 'personalize' in test."
        return {
            "student_id": id,
            "course_id": self.course_id,
            "item_id": self.block_id,
            "item_type": 'sga',  # ???
        }

    def get_submission(self, id=None):
        """
        Get student's most recent submission.
        """
        submissions = submissions_api.get_submissions(
            self.student_submission_id(id))
        if submissions:
            # If I understand docs correctly, most recent submission should
            # be first
            return submissions[0]

    def get_score(self, id=None):
        """
        Get student's current score.
        """
        score = submissions_api.get_score(self.student_submission_id(id))
        if score:
            return score['points_earned']

    @reify
    def score(self):
        return self.get_score()

    def student_view(self, context=None):
        """
        The primary view of the StaffGradedAssignmentXBlock, shown to students
        when viewing courses.
        """
        context = {
            "student_state": json.dumps(self.student_state()),
            "id": self.location.name.replace('.', '_')
        }
        if self.show_staff_grading_interface():
            context['is_course_staff'] = True
            self.update_staff_debug_context(context)

        fragment = Fragment()
        fragment.add_content(
            render_template(
                'templates/staff_graded_assignment/show.html',
                context
            )
        )
        fragment.add_css(_resource("static/css/edx_sga.css"))
        fragment.add_javascript(_resource("static/js/src/edx_sga.js"))
        fragment.initialize_js('StaffGradedAssignmentXBlock')
        return fragment

    def update_staff_debug_context(self, context):
        published = self.start
        context['is_released'] = published and published < _now()
        context['location'] = self.location
        context['category'] = type(self).__name__
        context['fields'] = [
            (name, field.read_from(self))
            for name, field in self.fields.items()]

    def student_state(self):
        """
        Returns a JSON serializable representation of student's state for
        rendering in client view.
        """
        submission = self.get_submission()
        if submission:
            uploaded = {"filename": submission['answer']['filename']}
        else:
            uploaded = None

        if self.annotated_sha1:
            annotated = {"filename": self.annotated_filename}
        else:
            annotated = None

        score = self.score
        if score is not None:
            graded = {'score': score, 'comment': self.comment}
        else:
            graded = None

        return {
            "uploaded": uploaded,
            "annotated": annotated,
            "graded": graded,
            "max_score": self.max_score(),
            "upload_allowed": self.upload_allowed(),
        }

    def staff_grading_data(self):
        def get_student_data():
            # Submissions doesn't have API for this, just use model directly
            students = SubmissionsStudent.objects.filter(
                course_id=self.course_id,
                item_id=self.block_id)
            for student in students:
                submission = self.get_submission(student.student_id)
                if not submission:
                    continue
                user = user_by_anonymous_id(student.student_id)
                module, _ = StudentModule.objects.get_or_create(
                    course_id=self.course_id,
                    module_state_key=self.location,
                    student=user,
                    defaults={
                        'state': '{}',
                        'module_type': self.category,
                    })
                state = json.loads(module.state)
                score = self.get_score(student.student_id)
                approved = score is not None
                if score is None:
                    score = state.get('staff_score')
                    needs_approval = score is not None
                else:
                    needs_approval = False
                instructor = self.is_instructor()
                yield {
                    'module_id': module.id,
                    'student_id': student.student_id,
                    'submission_id': submission['uuid'],
                    'username': module.student.username,
                    'fullname': module.student.profile.name,
                    'filename': submission['answer']["filename"],
                    'timestamp': submission['created_at'].strftime(
                        DateTime.DATETIME_FORMAT
                    ),
                    'score': score,
                    'approved': approved,
                    'needs_approval': instructor and needs_approval,
                    'may_grade': instructor or not approved,
                    'annotated': state.get("annotated_filename"),
                    'comment': state.get("comment", ''),
                }

        return {
            'assignments': list(get_student_data()),
            'max_score': self.max_score(),
        }

    def studio_view(self, context=None):
        try:
            cls = type(self)

            def none_to_empty(x):
                return x if x is not None else ''
            edit_fields = (
                (field, none_to_empty(getattr(self, field.name)), validator)
                for field, validator in (
                    (cls.display_name, 'string'),
                    (cls.points, 'number'),
                    (cls.weight, 'number'))
            )

            context = {
                'fields': edit_fields
            }
            fragment = Fragment()
            fragment.add_content(
                render_template(
                    'templates/staff_graded_assignment/edit.html',
                    context
                )
            )
            fragment.add_javascript(_resource("static/js/src/studio.js"))
            fragment.initialize_js('StaffGradedAssignmentXBlock')
            return fragment
        except:  # pragma: NO COVER
            log.error("Don't swallow my exceptions", exc_info=True)
            raise

    @XBlock.json_handler
    def save_sga(self, data, suffix=''):
        self.display_name = data.get('display_name', self.display_name)
        self.weight = data.get('weight', self.weight)

        # Validate points before saving
        points = data.get('points', self.points)
        # Check that we are an int
        try:
            points = int(points)
        except ValueError:
            raise JsonHandlerError(400, 'Points must be an integer')
        # Check that we are positive
        if points < 0:
            raise JsonHandlerError(400, 'Points must be a positive integer')
        self.points = points

    @XBlock.handler
    def upload_assignment(self, request, suffix=''):
        require(self.upload_allowed())
        upload = request.params['assignment']
        sha1 = _get_sha1(upload.file)
        answer = {
            "sha1": sha1,
            "filename": upload.file.name,
            "mimetype": mimetypes.guess_type(upload.file.name)[0],
        }
        student_id = self.student_submission_id()
        submissions_api.create_submission(student_id, answer)
        path = self._file_storage_path(sha1, upload.file.name)
        if not default_storage.exists(path):
            default_storage.save(path, File(upload.file))
        return Response(json_body=self.student_state())

    @XBlock.handler
    def staff_upload_annotated(self, request, suffix=''):
        require(self.is_course_staff())
        upload = request.params['annotated']
        module = StudentModule.objects.get(pk=request.params['module_id'])
        state = json.loads(module.state)
        state['annotated_sha1'] = sha1 = _get_sha1(upload.file)
        state['annotated_filename'] = filename = upload.file.name
        state['annotated_mimetype'] = mimetypes.guess_type(upload.file.name)[0]
        state['annotated_timestamp'] = _now().strftime(
            DateTime.DATETIME_FORMAT
        )
        path = self._file_storage_path(sha1, filename)
        if not default_storage.exists(path):
            default_storage.save(path, File(upload.file))
        module.state = json.dumps(state)
        module.save()
        return Response(json_body=self.staff_grading_data())

    @XBlock.handler
    def download_assignment(self, request, suffix=''):
        answer = self.get_submission()['answer']
        path = self._file_storage_path(answer['sha1'], answer['filename'])
        return self.download(path, answer['mimetype'], answer['filename'])

    @XBlock.handler
    def download_annotated(self, request, suffix=''):
        path = self._file_storage_path(
            self.annotated_sha1,
            self.annotated_filename,
        )
        return self.download(
            path,
            self.annotated_mimetype,
            self.annotated_filename
        )

    @XBlock.handler
    def staff_download(self, request, suffix=''):
        require(self.is_course_staff())
        submission = self.get_submission(request.params['student_id'])
        answer = submission['answer']
        path = self._file_storage_path(answer['sha1'], answer['filename'])
        return self.download(path, answer['mimetype'], answer['filename'])

    @XBlock.handler
    def staff_download_annotated(self, request, suffix=''):
        require(self.is_course_staff())
        module = StudentModule.objects.get(pk=request.params['module_id'])
        state = json.loads(module.state)
        path = self._file_storage_path(
            state['annotated_sha1'],
            state['annotated_filename']
        )
        return self.download(
            path,
            state['annotated_mimetype'],
            state['annotated_filename']
        )

    def download(self, path, mimetype, filename):
        BLOCK_SIZE = (1 << 10) * 8  # 8kb
        file = default_storage.open(path)
        app_iter = iter(partial(file.read, BLOCK_SIZE), '')
        return Response(
            app_iter=app_iter,
            content_type=mimetype,
            content_disposition="attachment; filename=" + filename)

    @XBlock.handler
    def get_staff_grading_data(self, request, suffix=''):
        require(self.is_course_staff())
        return Response(json_body=self.staff_grading_data())

    @XBlock.handler
    def enter_grade(self, request, suffix=''):
        require(self.is_course_staff())
        module = StudentModule.objects.get(pk=request.params['module_id'])
        state = json.loads(module.state)
        score = int(request.params['grade'])
        if self.is_instructor():
            uuid = request.params['submission_id']
            submissions_api.set_score(uuid, score, self.max_score())
        else:
            state['staff_score'] = score
        state['comment'] = request.params.get('comment', '')
        module.state = json.dumps(state)
        module.save()

        return Response(json_body=self.staff_grading_data())

    @XBlock.handler
    def remove_grade(self, request, suffix=''):
        require(self.is_course_staff())
        student_id = request.params['student_id']
        submissions_api.reset_score(student_id, self.course_id, self.block_id)
        module = StudentModule.objects.get(pk=request.params['module_id'])
        state = json.loads(module.state)
        state['staff_score'] = None
        state['comment'] = ''
        state['annotated_sha1'] = None
        state['annotated_filename'] = None
        state['annotated_mimetype'] = None
        state['annotated_timestamp'] = None
        module.state = json.dumps(state)
        module.save()
        return Response(json_body=self.staff_grading_data())

    def is_course_staff(self):
        return getattr(self.xmodule_runtime, 'user_is_staff', False)

    def is_instructor(self):
        return self.xmodule_runtime.get_user_role() == 'instructor'

    def show_staff_grading_interface(self):
        in_studio_preview = self.scope_ids.user_id is None
        return self.is_course_staff() and not in_studio_preview

    def past_due(self):
        due = get_extended_due_date(self)
        if due is not None:
            return _now() > due
        return False

    def upload_allowed(self):
        return not self.past_due() and self.score is None

    def _file_storage_path(self, sha1, filename):
        path = (
            '{loc.org}/{loc.course}/{loc.block_type}/{loc.block_id}'
            '/{sha1}{ext}'.format(
                loc=self.location,
                sha1=sha1,
                ext=os.path.splitext(filename)[1]
            )
        )
        return path


def _get_sha1(file):
    BLOCK_SIZE = 2**10 * 8  # 8kb
    sha1 = hashlib.sha1()
    for block in iter(partial(file.read, BLOCK_SIZE), ''):
        sha1.update(block)
    file.seek(0)
    return sha1.hexdigest()


def _resource(path):  # pragma: NO COVER
    """Handy helper for getting resources from our kit."""
    data = pkg_resources.resource_string(__name__, path)
    return data.decode("utf8")


def _now():
    return datetime.datetime.utcnow().replace(tzinfo=pytz.utc)


def load_resource(resource_path):  # pragma: NO COVER
    """
    Gets the content of a resource
    """
    resource_content = pkg_resources.resource_string(__name__, resource_path)
    return unicode(resource_content)


def render_template(template_path, context={}):  # pragma: NO COVER
    """
    Evaluate a template by resource path, applying the provided context
    """
    template_str = load_resource(template_path)
    template = Template(template_str)
    return template.render(Context(context))


def require(assertion):
    """
    Raises PermissionDenied if assertion is not true.
    """
    if not assertion:
        raise PermissionDenied
