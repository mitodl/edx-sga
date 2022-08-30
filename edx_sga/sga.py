"""
This block defines a Staff Graded Assignment.  Students are shown a rubric
and invited to upload a file which is then graded by staff.
"""
import json
import logging
import mimetypes
import os
from contextlib import closing
from zipfile import ZipFile

import six.moves.urllib.error
import six.moves.urllib.parse
import six.moves.urllib.request
import six

import pkg_resources
import pytz
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files import File
from django.core.files.storage import default_storage
from django.template import Context, Template
from django.utils.encoding import force_text
from django.utils.timezone import now as django_now
from django.utils.translation import gettext as _
from lms.djangoapps.courseware.models import StudentModule
from safe_lxml import etree
from common.djangoapps.student.models import user_by_anonymous_id
from submissions import api as submissions_api
from submissions.models import StudentItem as SubmissionsStudent
from submissions.models import Submission
from webob.response import Response
from xblock.core import XBlock
from xblock.exceptions import JsonHandlerError
from xblock.fields import DateTime, Float, Integer, Scope, String
from web_fragments.fragment import Fragment
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xmodule.contentstore.content import StaticContent
from xmodule.util.duedate import get_extended_due_date

from edx_sga.constants import ITEM_TYPE
from edx_sga.showanswer import ShowAnswerXBlockMixin
from edx_sga.tasks import get_zip_file_name, get_zip_file_path, zip_student_submissions
from edx_sga.utils import (
    file_contents_iter,
    get_file_modified_time_utc,
    get_file_storage_path,
    get_sha1,
    is_finalized_submission,
    utcnow,
)

log = logging.getLogger(__name__)


def reify(meth):
    """
    Decorator which caches value so it is only computed once.
    Keyword arguments:
    inst
    """

    def getter(inst):
        """
        Set value to meth name in dict and returns value.
        """
        value = meth(inst)
        inst.__dict__[meth.__name__] = value
        return value

    return property(getter)


class StaffGradedAssignmentXBlock(
    StudioEditableXBlockMixin, ShowAnswerXBlockMixin, XBlock
):
    """
    This block defines a Staff Graded Assignment.  Students are shown a rubric
    and invited to upload a file which is then graded by staff.
    """

    has_score = True
    icon_class = "problem"
    STUDENT_FILEUPLOAD_MAX_SIZE = 4 * 1000 * 1000  # 4 MB
    editable_fields = ("display_name", "points", "weight", "showanswer", "solution")

    display_name = String(
        display_name=_("Display Name"),
        default=_("Staff Graded Assignment"),
        scope=Scope.settings,
        help=_(
            "This name appears in the horizontal navigation at the top of " "the page."
        ),
    )

    weight = Float(
        display_name=_("Problem Weight"),
        help=_(
            "Defines the number of points each problem is worth. "
            "If the value is not set, the problem is worth the sum of the "
            "option point values."
        ),
        values={"min": 0, "step": 0.1},
        scope=Scope.settings,
    )

    points = Integer(
        display_name=_("Maximum score"),
        help=_("Maximum grade score given to assignment by staff."),
        default=100,
        scope=Scope.settings,
    )

    staff_score = Integer(
        display_name=_("Score assigned by non-instructor staff"),
        help=_(
            "Score will need to be approved by instructor before being " "published."
        ),
        default=None,
        scope=Scope.settings,
    )

    comment = String(
        display_name=_("Instructor comment"),
        default="",
        scope=Scope.user_state,
        help=_("Feedback given to student by instructor."),
    )

    annotated_sha1 = String(
        display_name=_("Annotated SHA1"),
        scope=Scope.user_state,
        default=None,
        help=_(
            "sha1 of the annotated file uploaded by the instructor for "
            "this assignment."
        ),
    )

    annotated_filename = String(
        display_name=_("Annotated file name"),
        scope=Scope.user_state,
        default=None,
        help=_("The name of the annotated file uploaded for this assignment."),
    )

    annotated_mimetype = String(
        display_name=_("Mime type of annotated file"),
        scope=Scope.user_state,
        default=None,
        help=_("The mimetype of the annotated file uploaded for this assignment."),
    )

    annotated_timestamp = DateTime(
        display_name=_("Timestamp"),
        scope=Scope.user_state,
        default=None,
        help=_("When the annotated file was uploaded"),
    )

    @classmethod
    def student_upload_max_size(cls):
        """
        returns max file size limit in system
        """
        return getattr(
            settings, "STUDENT_FILEUPLOAD_MAX_SIZE", cls.STUDENT_FILEUPLOAD_MAX_SIZE
        )

    @classmethod
    def file_size_over_limit(cls, file_obj):
        """
        checks if file size is under limit.
        """
        file_obj.seek(0, os.SEEK_END)
        return file_obj.tell() > cls.student_upload_max_size()

    @classmethod
    def parse_xml(cls, node, runtime, keys, id_generator):
        """
        Override default serialization to handle <solution /> elements
        """
        block = runtime.construct_xblock_from_class(cls, keys)

        for child in node:
            if child.tag == "solution":
                # convert child elements of <solution> into HTML for display
                block.solution = "".join(etree.tostring(subchild) for subchild in child)

        # Attributes become fields.
        # Note that a solution attribute here will override any solution XML element
        for name, value in node.items():  # lxml has no iteritems
            cls._set_field_if_present(block, name, value, {})

        return block

    def add_xml_to_node(self, node):
        """
        Override default serialization to output solution field as a separate child element.
        """
        super().add_xml_to_node(node)

        if "solution" in node.attrib:
            # Try outputting it as an XML element if we can
            solution = node.attrib["solution"]
            wrapped = f"<solution>{solution}</solution>"
            try:
                child = etree.fromstring(wrapped)
            except:  # pylint: disable=bare-except
                # Parsing exception, leave the solution as an attribute
                pass
            else:
                node.append(child)
                del node.attrib["solution"]

    @XBlock.json_handler
    def save_sga(self, data, suffix=""):
        # pylint: disable=unused-argument,raise-missing-from
        """
        Persist block data when updating settings in studio.
        """
        self.display_name = data.get("display_name", self.display_name)

        # Validate points before saving
        points = data.get("points", self.points)
        # Check that we are an int
        try:
            points = int(points)
        except ValueError:
            raise JsonHandlerError(400, "Points must be an integer")
        # Check that we are positive
        if points < 0:
            raise JsonHandlerError(400, "Points must be a positive integer")
        self.points = points

        # Validate weight before saving
        weight = data.get("weight", self.weight)
        # Check that weight is a float.
        if weight:
            try:
                weight = float(weight)
            except ValueError:
                raise JsonHandlerError(400, "Weight must be a decimal number")
            # Check that we are positive
            if weight < 0:
                raise JsonHandlerError(400, "Weight must be a positive decimal number")
        self.weight = weight

    @XBlock.handler
    def upload_assignment(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Save a students submission file.
        """
        require(self.upload_allowed())
        user = self.get_real_user()
        require(user)
        upload = request.params["assignment"]
        sha1 = get_sha1(upload.file)
        if self.file_size_over_limit(upload.file):
            size=self.student_upload_max_size()
            raise JsonHandlerError(
                413,
                f"Unable to upload file. Max size limit is {size}"
            )
        # Uploading an assignment represents a change of state with this user in this block,
        # so we need to ensure that the user has a StudentModule record, which represents that state.
        self.get_or_create_student_module(user)
        answer = {
            "sha1": sha1,
            "filename": upload.file.name,
            "mimetype": mimetypes.guess_type(upload.file.name)[0],
            "finalized": False,
        }
        student_item_dict = self.get_student_item_dict()
        submissions_api.create_submission(student_item_dict, answer)
        path = self.file_storage_path(sha1, upload.file.name)
        log.info(
            "Saving file: %s at path: %s for user: %s",
            upload.file.name,
            path,
            user.username,
        )
        if default_storage.exists(path):
            # save latest submission
            default_storage.delete(path)
        default_storage.save(path, File(upload.file))
        return Response(json_body=self.student_state())

    @XBlock.handler
    def finalize_uploaded_assignment(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Finalize a student's uploaded submission. This prevents further uploads for the
        given block, and makes the submission available to instructors for grading
        """
        submission_data = self.get_submission()
        require(self.upload_allowed(submission_data=submission_data))
        # Editing the Submission record directly since the API doesn't support it
        submission = Submission.objects.get(uuid=submission_data["uuid"])
        if not submission.answer.get("finalized"):
            submission.answer["finalized"] = True
            submission.submitted_at = django_now()
            submission.save()
        return Response(json_body=self.student_state())

    @XBlock.handler
    def staff_upload_annotated(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Save annotated assignment from staff.
        """
        require(self.is_course_staff())
        upload = request.params["annotated"]
        sha1 = get_sha1(upload.file)
        if self.file_size_over_limit(upload.file):
            size=self.student_upload_max_size()
            raise JsonHandlerError(
                413,
                f"Unable to upload file. Max size limit is {size}"
            )
        module = self.get_student_module(request.params["module_id"])
        state = json.loads(module.state)
        state["annotated_sha1"] = sha1
        state["annotated_filename"] = filename = upload.file.name
        state["annotated_mimetype"] = mimetypes.guess_type(upload.file.name)[0]
        state["annotated_timestamp"] = utcnow().strftime(DateTime.DATETIME_FORMAT)
        path = self.file_storage_path(sha1, filename)
        if not default_storage.exists(path):
            default_storage.save(path, File(upload.file))
        module.state = json.dumps(state)
        module.save()
        log.info(
            "staff_upload_annotated for course:%s module:%s student:%s ",
            module.course_id,
            module.module_state_key,
            module.student.username,
        )
        return Response(json_body=self.staff_grading_data())

    @XBlock.handler
    def download_assignment(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Fetch student assignment from storage and return it.
        """
        answer = self.get_submission()["answer"]
        path = self.file_storage_path(answer["sha1"], answer["filename"])
        return self.download(path, answer["mimetype"], answer["filename"])

    @XBlock.handler
    def download_annotated(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Fetch assignment with staff annotations from storage and return it.
        """
        path = self.file_storage_path(
            self.annotated_sha1,
            self.annotated_filename,
        )
        return self.download(path, self.annotated_mimetype, self.annotated_filename)

    @XBlock.handler
    def staff_download(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Return an assignment file requested by staff.
        """
        require(self.is_course_staff())
        submission = self.get_submission(request.params["student_id"])
        answer = submission["answer"]
        path = self.file_storage_path(answer["sha1"], answer["filename"])
        return self.download(
            path, answer["mimetype"], answer["filename"], require_staff=True
        )

    @XBlock.handler
    def staff_download_annotated(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Return annotated assignment file requested by staff.
        """
        require(self.is_course_staff())
        module = self.get_student_module(request.params["module_id"])
        state = json.loads(module.state)
        path = self.file_storage_path(
            state["annotated_sha1"], state["annotated_filename"]
        )
        return self.download(
            path,
            state["annotated_mimetype"],
            state["annotated_filename"],
            require_staff=True,
        )

    @XBlock.handler
    def get_staff_grading_data(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Return the html for the staff grading view
        """
        require(self.is_course_staff())
        return Response(json_body=self.staff_grading_data())

    @XBlock.handler
    def enter_grade(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Persist a score for a student given by staff.
        """
        require(self.is_course_staff())
        score = request.params.get("grade", None)
        module = self.get_student_module(request.params["module_id"])
        if not score:
            return Response(
                json_body=self.validate_score_message(
                    module.course_id, module.student.username
                )
            )

        state = json.loads(module.state)
        try:
            score = int(score)
        except ValueError:
            return Response(
                json_body=self.validate_score_message(
                    module.course_id, module.student.username
                )
            )

        if self.is_instructor():
            uuid = request.params["submission_id"]
            submissions_api.set_score(uuid, score, self.max_score())
        else:
            state["staff_score"] = score
        state["comment"] = request.params.get("comment", "")
        module.state = json.dumps(state)
        module.save()
        log.info(
            "enter_grade for course:%s module:%s student:%s",
            module.course_id,
            module.module_state_key,
            module.student.username,
        )

        return Response(json_body=self.staff_grading_data())

    @XBlock.handler
    def remove_grade(self, request, suffix=""):
        # pylint: disable=unused-argument
        """
        Reset a students score request by staff.
        """
        require(self.is_course_staff())
        student_id = request.params["student_id"]
        submissions_api.reset_score(student_id, self.block_course_id, self.block_id)
        module = self.get_student_module(request.params["module_id"])
        state = json.loads(module.state)
        state["staff_score"] = None
        state["comment"] = ""
        state["annotated_sha1"] = None
        state["annotated_filename"] = None
        state["annotated_mimetype"] = None
        state["annotated_timestamp"] = None
        module.state = json.dumps(state)
        module.save()
        log.info(
            "remove_grade for course:%s module:%s student:%s",
            module.course_id,
            module.module_state_key,
            module.student.username,
        )
        return Response(json_body=self.staff_grading_data())

    @XBlock.handler
    def prepare_download_submissions(
        self, request, suffix=""
    ):  # pylint: disable=unused-argument
        """
        Runs a async task that collects submissions in background and zip them.
        """
        # pylint: disable=no-member
        require(self.is_course_staff())
        user = self.get_real_user()
        require(user)
        zip_file_ready = False
        location = str(self.location)

        if self.is_zip_file_available(user):
            log.info(
                "Zip file already available for block: %s for instructor: %s",
                location,
                user.username,
            )
            assignments = self.get_sorted_submissions()
            if assignments:
                last_assignment_date = assignments[0]["timestamp"].astimezone(pytz.utc)
                zip_file_path = get_zip_file_path(
                    user.username, self.block_course_id, self.block_id, self.location
                )
                zip_file_time = get_file_modified_time_utc(zip_file_path)
                log.info(
                    "Zip file modified time: %s, last zip file time: %s for block: %s for instructor: %s",
                    last_assignment_date,
                    zip_file_time,
                    location,
                    user.username,
                )
                # if last zip file is older the last submission then recreate task
                if zip_file_time >= last_assignment_date:
                    zip_file_ready = True

                # check if some one reset submission. If yes the recreate zip file
                assignment_count = len(assignments)
                if self.count_archive_files(user) != assignment_count:
                    zip_file_ready = False

        if not zip_file_ready:
            log.info(
                "Creating new zip file for block: %s for instructor: %s",
                location,
                user.username,
            )
            zip_student_submissions.delay(
                self.block_course_id, self.block_id, location, user.username
            )

        return Response(json_body={"downloadable": zip_file_ready})

    @XBlock.handler
    def download_submissions(
        self, request, suffix=""
    ):  # pylint: disable=unused-argument
        """
        Api for downloading zip file which consist of all students submissions.
        """
        # pylint: disable=no-member
        require(self.is_course_staff())
        user = self.get_real_user()
        require(user)
        try:
            zip_file_path = get_zip_file_path(
                user.username, self.block_course_id, self.block_id, self.location
            )
            zip_file_name = get_zip_file_name(
                user.username, self.block_course_id, self.block_id
            )
            return Response(
                app_iter=file_contents_iter(zip_file_path),
                content_type="application/zip",
                content_disposition="attachment; filename=" + zip_file_name,
            )
        except OSError:
            return Response(
                "Sorry, submissions cannot be found. Press Collect ALL Submissions button or"
                f" contact {settings.TECH_SUPPORT_EMAIL} if you issue is consistent",
                status_code=404,
            )

    @XBlock.handler
    def download_submissions_status(
        self, request, suffix=""
    ):  # pylint: disable=unused-argument
        """
        returns True if zip file is available for download
        """
        require(self.is_course_staff())
        user = self.get_real_user()
        require(user)
        return Response(json_body={"zip_available": self.is_zip_file_available(user)})

    def student_view(self, context=None):
        # pylint: disable=no-member
        """
        The primary view of the StaffGradedAssignmentXBlock, shown to students
        when viewing courses.
        """
        context = {
            "student_state": json.dumps(self.student_state()),
            "id": self.location.name.replace(".", "_"),
            "max_file_size": self.student_upload_max_size(),
            "support_email": settings.TECH_SUPPORT_EMAIL,
        }
        if self.show_staff_grading_interface():
            context["is_course_staff"] = True
            self.update_staff_debug_context(context)

        fragment = Fragment()
        fragment.add_content(
            render_template("templates/staff_graded_assignment/show.html", context)
        )
        fragment.add_css(_resource("static/css/edx_sga.css"))
        fragment.add_javascript(_resource("static/js/src/edx_sga.js"))
        fragment.add_javascript(_resource("static/js/src/jquery.tablesorter.min.js"))
        fragment.initialize_js("StaffGradedAssignmentXBlock")
        return fragment

    def studio_view(self, context=None):
        """
        Render a form for editing this XBlock
        """
        # this method only exists to provide context=None for backwards compat
        return super().studio_view(context)

    def clear_student_state(self, *args, **kwargs):
        """
        For a given user, clears submissions and uploaded files for this XBlock.

        Staff users are able to delete a learner's state for a block in LMS. When that capability is
        used, the block's "clear_student_state" function is called if it exists.
        """
        student_id = kwargs["user_id"]
        for submission in submissions_api.get_submissions(
            self.get_student_item_dict(student_id)
        ):
            submission_file_sha1 = submission["answer"].get("sha1")
            submission_filename = submission["answer"].get("filename")
            submission_file_path = self.file_storage_path(
                submission_file_sha1, submission_filename
            )
            if default_storage.exists(submission_file_path):
                default_storage.delete(submission_file_path)
            submissions_api.reset_score(
                student_id, self.block_course_id, self.block_id, clear_state=True
            )

    def max_score(self):
        """
        Return the maximum score possible.
        """
        return self.points

    @reify
    def block_id(self):
        """
        Return the usage_id of the block.
        """
        return str(self.scope_ids.usage_id)

    @reify
    def block_course_id(self):
        """
        Return the course_id of the block.
        """
        return str(self.course_id)

    def get_student_item_dict(self, student_id=None):
        # pylint: disable=no-member
        """
        Returns dict required by the submissions app for creating and
        retrieving submissions for a particular student.
        """
        if student_id is None:
            student_id = self.xmodule_runtime.anonymous_student_id
            assert student_id != ("MOCK", "Forgot to call 'personalize' in test.")
        return {
            "student_id": student_id,
            "course_id": self.block_course_id,
            "item_id": self.block_id,
            "item_type": ITEM_TYPE,
        }

    def get_submission(self, student_id=None):
        """
        Get student's most recent submission.
        """
        submissions = submissions_api.get_submissions(
            self.get_student_item_dict(student_id)
        )
        if submissions:
            # If I understand docs correctly, most recent submission should
            # be first
            return submissions[0]

        return None

    def get_score(self, student_id=None):
        """
        Return student's current score.
        """
        score = submissions_api.get_score(self.get_student_item_dict(student_id))
        if score:
            return score["points_earned"]

        return None

    @reify
    def score(self):
        """
        Return score from submissions.
        """
        return self.get_score()

    def update_staff_debug_context(self, context):
        # pylint: disable=no-member
        """
        Add context info for the Staff Debug interface.
        """
        published = self.start
        context["is_released"] = published and published < utcnow()
        context["location"] = self.location
        context["category"] = type(self).__name__
        context["fields"] = [
            (name, field.read_from(self)) for name, field in self.fields.items()
        ]

    def get_student_module(self, module_id):
        """
        Returns a StudentModule that matches the given id

        Args:
            module_id (int): The module id

        Returns:
            StudentModule: A StudentModule object
        """
        return StudentModule.objects.get(pk=module_id)

    def get_or_create_student_module(self, user):
        """
        Gets or creates a StudentModule for the given user for this block

        Returns:
            StudentModule: A StudentModule object
        """
        # pylint: disable=no-member
        student_module, created = StudentModule.objects.get_or_create(
            course_id=self.course_id,
            module_state_key=self.location,
            student=user,
            defaults={
                "state": "{}",
                "module_type": self.category,
            },
        )
        if created:
            log.info(
                "Created student module %s [course: %s] [student: %s]",
                student_module.module_state_key,
                student_module.course_id,
                student_module.student.username,
            )
        return student_module

    def student_state(self):
        """
        Returns a JSON serializable representation of student's state for
        rendering in client view.
        """
        submission = self.get_submission()
        if submission:
            uploaded = {"filename": submission["answer"]["filename"]}
        else:
            uploaded = None

        if self.annotated_sha1:
            annotated = {"filename": force_text(self.annotated_filename)}
        else:
            annotated = None

        score = self.score
        if score is not None:
            graded = {"score": score, "comment": force_text(self.comment)}
        else:
            graded = None

        if self.answer_available():
            solution = self.runtime.replace_urls(force_text(self.solution))
        else:
            solution = ""
        # pylint: disable=no-member
        return {
            "display_name": force_text(self.display_name),
            "uploaded": uploaded,
            "annotated": annotated,
            "graded": graded,
            "max_score": self.max_score(),
            "upload_allowed": self.upload_allowed(submission_data=submission),
            "solution": solution,
            "base_asset_url": StaticContent.get_base_url_path_for_course_assets(
                self.location.course_key
            ),
        }

    def staff_grading_data(self):
        """
        Return student assignment information for display on the
        grading screen.
        """

        def get_student_data():
            """
            Returns a dict of student assignment information along with
            annotated file name, student id and module id, this
            information will be used on grading screen
            """
            # Submissions doesn't have API for this, just use model directly.
            students = SubmissionsStudent.objects.filter(
                course_id=self.course_id, item_id=self.block_id
            )
            for student in students:
                submission = self.get_submission(student.student_id)
                if not submission:
                    continue
                user = user_by_anonymous_id(student.student_id)
                student_module = self.get_or_create_student_module(user)
                state = json.loads(student_module.state)
                score = self.get_score(student.student_id)
                approved = score is not None
                if score is None:
                    score = state.get("staff_score")
                    needs_approval = score is not None
                else:
                    needs_approval = False
                instructor = self.is_instructor()
                yield {
                    "module_id": student_module.id,
                    "student_id": student.student_id,
                    "submission_id": submission["uuid"],
                    "username": student_module.student.username,
                    "fullname": student_module.student.profile.name,
                    "filename": submission["answer"]["filename"],
                    "timestamp": submission["created_at"].strftime(
                        DateTime.DATETIME_FORMAT
                    ),
                    "score": score,
                    "approved": approved,
                    "needs_approval": instructor and needs_approval,
                    "may_grade": instructor or not approved,
                    "annotated": force_text(state.get("annotated_filename", "")),
                    "comment": force_text(state.get("comment", "")),
                    "finalized": is_finalized_submission(submission_data=submission),
                }

        return {
            "assignments": list(get_student_data()),
            "max_score": self.max_score(),
            "display_name": force_text(self.display_name),
        }

    def get_sorted_submissions(self):
        """returns student recent assignments sorted on date"""
        assignments = []
        submissions = submissions_api.get_all_submissions(
            self.course_id, self.block_id, ITEM_TYPE
        )

        for submission in submissions:
            if is_finalized_submission(submission_data=submission):
                assignments.append(
                    {
                        "submission_id": submission["uuid"],
                        "filename": submission["answer"]["filename"],
                        "timestamp": submission["submitted_at"]
                        or submission["created_at"],
                    }
                )

        assignments.sort(key=lambda assignment: assignment["timestamp"], reverse=True)
        return assignments

    def download(self, path, mime_type, filename, require_staff=False):
        """
        Return a file from storage and return in a Response.
        """
        try:
            content_disposition = "attachment; filename*=UTF-8''"
            content_disposition += six.moves.urllib.parse.quote(
                filename.encode("utf-8")
            )
            output = Response(
                app_iter=file_contents_iter(path),
                content_type=mime_type,
                content_disposition=content_disposition,
            )
            return output
        except OSError:
            if require_staff:
                return Response(
                    f"Sorry, assignment {filename.encode('utf-8')} cannot be found at"
                    f" {path}. Please contact {settings.TECH_SUPPORT_EMAIL}",
                    status_code=404,
                )
            return Response(
                f"Sorry, the file you uploaded, {filename.encode('utf-8')}, cannot be"
                " found. Please try uploading it again or contact"
                " course staff",
                status_code=404,
            )

    def validate_score_message(
        self, course_id, username
    ):  # lint-amnesty, pylint: disable=missing-function-docstring
        # pylint: disable=no-member
        log.error(
            "enter_grade: invalid grade submitted for course:%s module:%s student:%s",
            course_id,
            self.location,
            username,
        )
        return {"error": "Please enter valid grade"}

    def is_course_staff(self):
        # pylint: disable=no-member
        """
        Check if user is course staff.
        """
        return getattr(self.xmodule_runtime, "user_is_staff", False)

    def is_instructor(self):
        # pylint: disable=no-member
        """
        Check if user role is instructor.
        """
        return self.xmodule_runtime.get_user_role() == "instructor"

    def show_staff_grading_interface(self):
        """
        Return if current user is staff and not in studio.
        """
        in_studio_preview = self.scope_ids.user_id is None
        return self.is_course_staff() and not in_studio_preview

    def past_due(self):
        """
        Return whether due date has passed.
        """
        due = get_extended_due_date(self)
        try:
            graceperiod = self.graceperiod
        except AttributeError:
            # graceperiod and due are defined in InheritanceMixin
            # It's used automatically in edX but the unit tests will need to mock it out
            graceperiod = None

        if graceperiod is not None and due:
            close_date = due + graceperiod
        else:
            close_date = due

        if close_date is not None:
            return utcnow() > close_date
        return False

    def upload_allowed(self, submission_data=None):
        """
        Return whether student is allowed to upload an assignment.
        """
        submission_data = (
            submission_data if submission_data is not None else self.get_submission()
        )
        return (
            not self.past_due()
            and self.score is None
            and not is_finalized_submission(submission_data)
        )

    def file_storage_path(self, file_hash, original_filename):
        # pylint: disable=no-member
        """
        Helper method to get the path of an uploaded file
        """
        return get_file_storage_path(self.location, file_hash, original_filename)

    def is_zip_file_available(self, user):
        """
        returns True if zip file exists.
        """
        # pylint: disable=no-member
        zip_file_path = get_zip_file_path(
            user.username, self.block_course_id, self.block_id, self.location
        )
        return default_storage.exists(zip_file_path)

    def count_archive_files(self, user):
        """
        returns number of files archive in zip.
        """
        # pylint: disable=no-member
        zip_file_path = get_zip_file_path(
            user.username, self.block_course_id, self.block_id, self.location
        )
        with default_storage.open(zip_file_path, "rb") as zip_file:
            with closing(ZipFile(zip_file)) as archive:
                return len(archive.infolist())

    def get_real_user(self):
        """returns session user"""
        # pylint: disable=no-member
        return self.runtime.get_real_user(self.xmodule_runtime.anonymous_student_id)

    def correctness_available(self):
        """
        For SGA is_correct just means the user submitted the problem, which we always know one way or the other
        """
        return True

    def is_past_due(self):
        """
        Is it now past this problem's due date?
        """
        return self.past_due()

    def is_correct(self):
        """
        For SGA we show the answer as soon as we know the user has given us their submission
        """
        return self.has_attempted()

    def has_attempted(self):
        """
        True if the student has already attempted this problem
        """
        submission = self.get_submission()
        if not submission:
            return False
        return submission["answer"]["finalized"]

    def can_attempt(self):
        """
        True if the student can attempt the problem
        """
        return not self.has_attempted()

    def runtime_user_is_staff(self):
        """
        Is the logged in user a staff user?
        """
        return self.is_course_staff()


def _resource(path):  # pragma: NO COVER
    """
    Handy helper for getting resources from our kit.
    """
    data = pkg_resources.resource_string(__name__, path)
    return data.decode("utf8")


def load_resource(resource_path):  # pragma: NO COVER
    """
    Gets the content of a resource
    """
    resource_content = pkg_resources.resource_string(__name__, resource_path)
    return str(resource_content.decode("utf8"))


def render_template(template_path, context=None):  # pragma: NO COVER
    """
    Evaluate a template by resource path, applying the provided context.
    """
    if context is None:
        context = {}

    template_str = load_resource(template_path)
    template = Template(template_str)
    return template.render(Context(context))


def require(assertion):
    """
    Raises PermissionDenied if assertion is not true.
    """
    if not assertion:
        raise PermissionDenied
