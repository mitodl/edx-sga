"""
Tests for SGA
"""
# pylint: disable=imported-auth-user, unspecified-encoding
import datetime
import html
import json
import os
import shutil
import tempfile
from unittest import mock

import six.moves.urllib.error
import six.moves.urllib.parse
import six.moves.urllib.request
import pytz
from ddt import data, ddt, unpack
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.test.utils import override_settings
from lms.djangoapps.courseware import module_render as render
from lms.djangoapps.courseware.models import StudentModule
from lms.djangoapps.courseware.tests.factories import StaffFactory
from opaque_keys.edx.locations import Location
from opaque_keys.edx.locator import CourseLocator
from common.djangoapps.student.models import UserProfile, anonymous_id_for_user
from common.djangoapps.student.tests.factories import AdminFactory
from submissions import api as submissions_api
from submissions.models import StudentItem
from xblock.field_data import DictFieldData
from xblock.fields import ScopeIds
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore.xml_exporter import export_course_to_xml
from xmodule.modulestore.xml_importer import import_course_from_xml


from edx_sga.constants import ShowAnswer
from edx_sga.sga import StaffGradedAssignmentXBlock
from edx_sga.tests.common import (
    DummyResource,
    TempfileMixin,
    get_sha1,
    is_near_now,
    parse_timestamp,
    reformat_xml,
)


@ddt
class StaffGradedAssignmentXblockTests(TempfileMixin, ModuleStoreTestCase):
    """
    Create a SGA block with mock data.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.set_up_temp_directory()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.tear_down_temp_directory()

    def setUp(self):
        """
        Creates a test course ID, mocks the runtime, and creates a fake storage
        engine for use in all tests
        """
        super().setUp()
        self.course = CourseFactory.create(org="foo", number="bar", display_name="baz")
        self.descriptor = ItemFactory(category="pure", parent=self.course)
        self.course_id = self.course.id
        self.instructor = StaffFactory.create(course_key=self.course_id)
        self.student_data = mock.Mock()
        self.staff = AdminFactory.create(password="test")
        self.runtime = self.make_runtime()
        self.scope_ids = self.make_scope_ids(self.runtime)

    def make_runtime(self, **kwargs):
        """
        Make a runtime
        """
        runtime, _ = render.get_module_system_for_user(
            self.instructor,
            self.student_data,
            self.descriptor,
            self.course.id,
            mock.Mock(),
            mock.Mock(),
            mock.Mock(),
            course=self.course,
            # not sure why this isn't working, if set to true it looks for
            # 'display_name_with_default_escaped' field that doesn't exist in SGA
            wrap_xmodule_display=False,
            **kwargs,
        )
        return runtime

    def make_scope_ids(self, runtime):
        """
        Make scope ids
        """
        # Not sure if this is a valid block type, might be sufficient for testing purposes
        block_type = "sga"
        def_id = runtime.id_generator.create_definition(block_type)
        return ScopeIds("user", block_type, def_id, self.descriptor.location)

    def make_one(self, display_name=None, **kw):
        """
        Creates a XBlock SGA for testing purpose.
        """
        field_data = DictFieldData(kw)
        block = StaffGradedAssignmentXBlock(self.runtime, field_data, self.scope_ids)
        block.location = Location("foo", "bar", "baz", "category", "name", "revision")

        block.xmodule_runtime = self.runtime
        block.course_id = self.course_id
        block.category = "problem"

        if display_name:
            block.display_name = display_name

        block.start = datetime.datetime(2010, 5, 12, 2, 42, tzinfo=pytz.utc)
        modulestore().create_item(
            self.staff.username,
            block.location.course_key,
            block.location.block_type,
            block.location.block_id,
        )
        return block

    def make_student(self, block, name, make_state=True, **state):
        """
        Create a student along with submission state.
        """
        answer = {}
        module = None
        for key in ("sha1", "mimetype", "filename", "finalized"):
            if key in state:
                answer[key] = state.pop(key)
        score = state.pop("score", None)

        with transaction.atomic():
            user = User(username=name, email=f"{name}@example.com")
            user.save()
            profile = UserProfile(user=user, name=name)
            profile.save()
            if make_state:
                module = StudentModule(
                    module_state_key=block.location,
                    student=user,
                    course_id=self.course_id,
                    state=json.dumps(state),
                )
                module.save()

            anonymous_id = anonymous_id_for_user(user, self.course_id)
            item = StudentItem(
                student_id=anonymous_id,
                course_id=self.course_id,
                item_id=block.block_id,
                item_type="sga",
            )
            item.save()

            if answer:
                student_id = block.get_student_item_dict(anonymous_id)
                submission = submissions_api.create_submission(student_id, answer)
                if score is not None:
                    submissions_api.set_score(
                        submission["uuid"], score, block.max_score()
                    )
            else:
                submission = None

            self.addCleanup(item.delete)
            self.addCleanup(profile.delete)
            self.addCleanup(user.delete)

            if make_state:
                self.addCleanup(module.delete)
                return {"module": module, "item": item, "submission": submission}

            return {"item": item, "submission": submission}

    def personalize(self, block, module, item, submission):
        # pylint: disable=unused-argument
        """
        Set values on block from student state.
        """
        student_module = StudentModule.objects.get(pk=module.id)
        state = json.loads(student_module.state)
        for key, value in state.items():
            setattr(block, key, value)
        self.runtime.anonymous_student_id = item.student_id

    def test_ctor(self):
        """
        Test points are set correctly.
        """
        block = self.make_one(points=10)
        self.assertEqual(block.display_name, "Staff Graded Assignment")
        self.assertEqual(block.points, 10)

    def test_max_score(self):
        """
        Text max score is set correctly.
        """
        block = self.make_one(points=20)
        self.assertEqual(block.max_score(), 20)

    def test_max_score_integer(self):
        """
        Test assigning a float max score is rounded to nearest integer.
        """
        block = self.make_one(points=20.4)
        self.assertEqual(block.max_score(), 20)

    @override_settings(TECH_SUPPORT_EMAIL="foo@example.com")
    @mock.patch("edx_sga.sga._resource", DummyResource)
    @mock.patch("edx_sga.sga.render_template")
    @mock.patch("edx_sga.sga.Fragment")
    def test_student_view(self, fragment, render_template):
        """
        Test student view renders correctly.
        """
        block = self.make_one("Custom name")
        self.personalize(block, **self.make_student(block, "fred"))
        fragment = block.student_view()
        render_template.assert_called_once()
        template_arg = render_template.call_args[0][0]
        self.assertEqual(template_arg, "templates/staff_graded_assignment/show.html")
        context = render_template.call_args[0][1]
        self.assertEqual(context["is_course_staff"], True)
        self.assertEqual(context["id"], "name")
        self.assertEqual(context["support_email"], "foo@example.com")
        student_state = json.loads(context["student_state"])
        self.assertEqual(student_state["display_name"], "Custom name")
        self.assertEqual(student_state["uploaded"], None)
        self.assertEqual(student_state["annotated"], None)
        self.assertEqual(student_state["upload_allowed"], True)
        self.assertEqual(student_state["max_score"], 100)
        self.assertEqual(student_state["graded"], None)
        # pylint: disable=no-member
        fragment.add_css.assert_called_once_with(
            DummyResource("static/css/edx_sga.css")
        )
        fragment.initialize_js.assert_called_once_with("StaffGradedAssignmentXBlock")

    @mock.patch("edx_sga.sga._resource", DummyResource)
    @mock.patch("edx_sga.sga.render_template")
    @mock.patch("edx_sga.sga.Fragment")
    def test_student_view_with_upload(self, fragment, render_template):
        # pylint: disable=unused-argument
        """
        Test student is able to upload assignment correctly.
        """
        block = self.make_one()
        self.personalize(
            block, **self.make_student(block, 'fred"', sha1="foo", filename="foo.bar")
        )
        block.student_view()
        context = render_template.call_args[0][1]
        student_state = json.loads(context["student_state"])
        self.assertEqual(student_state["uploaded"], {"filename": "foo.bar"})

    @mock.patch("edx_sga.sga._resource", DummyResource)
    @mock.patch("edx_sga.sga.render_template")
    @mock.patch("edx_sga.sga.Fragment")
    def test_student_view_with_annotated(self, fragment, render_template):
        # pylint: disable=unused-argument
        """
        Test student view shows annotated files correctly.
        """
        block = self.make_one(annotated_sha1="foo", annotated_filename="foo.bar")
        self.personalize(block, **self.make_student(block, "fred"))
        block.student_view()
        context = render_template.call_args[0][1]
        student_state = json.loads(context["student_state"])
        self.assertEqual(student_state["annotated"], {"filename": "foo.bar"})

    @mock.patch("edx_sga.sga._resource", DummyResource)
    @mock.patch("edx_sga.sga.render_template")
    @mock.patch("edx_sga.sga.Fragment")
    def test_student_view_with_score(self, fragment, render_template):
        """
        Tests scores are displayed correctly on student view.
        """
        block = self.make_one()
        self.personalize(
            block, **self.make_student(block, "fred", filename="foo.txt", score=10)
        )
        fragment = block.student_view()
        render_template.assert_called_once()
        template_arg = render_template.call_args[0][0]
        self.assertEqual(template_arg, "templates/staff_graded_assignment/show.html")
        context = render_template.call_args[0][1]
        self.assertEqual(context["is_course_staff"], True)
        self.assertEqual(context["id"], "name")
        student_state = json.loads(context["student_state"])
        self.assertEqual(student_state["display_name"], "Staff Graded Assignment")
        self.assertEqual(student_state["uploaded"], {"filename": "foo.txt"})
        self.assertEqual(student_state["annotated"], None)
        self.assertEqual(student_state["upload_allowed"], False)
        self.assertEqual(student_state["max_score"], 100)
        self.assertEqual(student_state["graded"], {"comment": "", "score": 10})
        # pylint: disable=no-member
        fragment.add_css.assert_called_once_with(
            DummyResource("static/css/edx_sga.css")
        )
        fragment.initialize_js.assert_called_once_with("StaffGradedAssignmentXBlock")

    def test_studio_view(self):
        """
        Test studio view is using the StudioEditableXBlockMixin function
        """
        with mock.patch(
            "edx_sga.sga.StudioEditableXBlockMixin.studio_view"
        ) as studio_view_mock:
            block = self.make_one()
            block.studio_view()
        studio_view_mock.assert_called_once_with(None)

    def test_save_sga(self):
        """
        Tests save SGA  block on studio.
        """

        def weights_positive_float_test():
            """
            tests weight is non negative float.
            """
            orig_weight = 11.0

            # Test negative weight doesn't work
            block.save_sga(
                mock.Mock(
                    method="POST",
                    body=json.dumps(
                        {"display_name": "Test Block", "points": "100", "weight": -10.0}
                    ),
                )
            )
            self.assertEqual(block.weight, orig_weight)

            # Test string weight doesn't work
            block.save_sga(
                mock.Mock(
                    method="POST",
                    body=json.dumps(
                        {"display_name": "Test Block", "points": "100", "weight": "a"}
                    ),
                )
            )
            self.assertEqual(block.weight, orig_weight)

        def point_positive_int_test():
            """
            Tests point is positive number.
            """
            # Test negative doesn't work
            block.save_sga(
                mock.Mock(
                    method="POST",
                    body=json.dumps(
                        {"display_name": "Test Block", "points": "-10", "weight": 11}
                    ),
                )
            )
            self.assertEqual(block.points, orig_score)

            # Test float doesn't work
            block.save_sga(
                mock.Mock(
                    method="POST",
                    body=json.dumps(
                        {"display_name": "Test Block", "points": "24.5", "weight": 11}
                    ),
                )
            )
            self.assertEqual(block.points, orig_score)

        orig_score = 23
        block = self.make_one()
        block.save_sga(mock.Mock(body="{}"))
        self.assertEqual(block.display_name, "Staff Graded Assignment")
        self.assertEqual(block.points, 100)
        self.assertEqual(block.weight, None)
        block.save_sga(
            mock.Mock(
                method="POST",
                body=json.dumps(
                    {
                        "display_name": "Test Block",
                        "points": str(orig_score),
                        "weight": 11,
                    }
                ),
            )
        )
        self.assertEqual(block.display_name, "Test Block")
        self.assertEqual(block.points, orig_score)
        self.assertEqual(block.weight, 11)

        point_positive_int_test()
        weights_positive_float_test()

    def test_upload_download_assignment(self):
        """
        Tests upload and download assignment for non staff.
        """
        block = self.make_one()
        self.personalize(block, **self.make_student(block, "fred"))
        with self.dummy_upload("text.txt") as (upload, expected):
            block.upload_assignment(mock.Mock(params={"assignment": upload}))
        response = block.download_assignment(None)
        self.assertEqual(response.body, expected)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(  # lint-amnesty
                "", "test_notfound.txt"
            ),  # lint-amnesty
        ):
            response = block.download_assignment(None)
            self.assertEqual(response.status_code, 404)

    def test_finalize_uploaded_assignment(self):
        """
        Tests that finalize_uploaded_assignment sets a submission to be finalized
        """
        block = self.make_one()
        created_student_data = self.make_student(
            block, "fred1", finalized=False, filename="answer"
        )
        self.personalize(block, **created_student_data)
        submission_data = created_student_data["submission"]
        response = block.finalize_uploaded_assignment(mock.Mock(method="POST"))
        recent_submission_data = block.get_submission()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, block.student_state())
        self.assertEqual(submission_data["uuid"], recent_submission_data["uuid"])
        self.assertTrue(recent_submission_data["answer"]["finalized"])

    def test_staff_upload_download_annotated(self):
        """
        Tests upload and download of annotated staff files.
        """
        block = self.make_one()
        fred = self.make_student(block, "fred1")["module"]
        with self.dummy_upload("test.txt") as (upload, expected):
            block.staff_upload_annotated(
                mock.Mock(params={"annotated": upload, "module_id": fred.id})
            )
        response = block.staff_download_annotated(
            mock.Mock(params={"module_id": fred.id})
        )
        self.assertEqual(response.body, expected)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(  # lint-amnesty
                "", "test_notfound.txt"
            ),  # lint-amnesty
        ):
            response = block.staff_download_annotated(
                mock.Mock(params={"module_id": fred.id})
            )
            self.assertEqual(response.status_code, 404)

    def test_staff_upload_annotated_state(self):
        """
        Test state recorded in the module state when staff_upload_annotated is called
        """
        block = self.make_one()
        fred = self.make_student(block, "fred1")["module"]

        with self.dummy_upload("testa.txt") as (upload, _):
            block.upload_assignment(mock.Mock(params={"assignment": upload}))
        block.finalize_uploaded_assignment(mock.Mock(method="POST"))

        with self.dummy_upload("testb.txt") as (upload, expected):
            request = mock.Mock(params={"annotated": upload, "module_id": fred.id})
            resp = block.staff_upload_annotated(request)
        assert resp.json == block.staff_grading_data()
        state = json.loads(block.get_student_module(fred.id).state)
        assert state["annotated_mimetype"] == "text/plain"
        parsed_date = parse_timestamp(state["annotated_timestamp"])
        assert is_near_now(parsed_date)
        assert state["annotated_filename"].endswith("testb.txt")
        assert state["annotated_sha1"] == get_sha1(expected)

    def test_download_annotated(self):
        """
        Test download annotated assignment for non staff.
        """
        block = self.make_one()
        students_info = [
            ["fred2", "test_fred.txt", "student 1"],
            ["foo2", "test_foo.txt", "student 2"],
        ]
        students = []
        for student_name, filename, text in students_info:
            student = self.make_student(block, student_name)
            with self.dummy_upload(filename, text) as (upload, __):
                block.staff_upload_annotated(
                    mock.Mock(
                        params={"annotated": upload, "module_id": student["module"].id}
                    )
                )
            students.append((student, text))

        for student, text in students:
            self.personalize(block, **student)
            response = block.download_annotated(None)
            self.assertEqual(response.body, text)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(  # lint-amnesty
                "", "test_notfound.txt"
            ),  # lint-amnesty
        ):
            response = block.download_annotated(None)
            self.assertEqual(response.status_code, 404)

    def test_staff_download(self):
        """
        Test validate each student assignment for staff download.
        """
        students = []
        block = self.make_one()
        students_info = [
            ["fred2", "test_fred.txt", "student 1"],
            ["foo2", "test_foo.txt", "student 2"],
        ]
        for student_name, filename, text in students_info:
            student = self.make_student(block, student_name)
            self.personalize(block, **student)
            with self.dummy_upload(filename, text) as (upload, __):
                block.upload_assignment(mock.Mock(params={"assignment": upload}))
            students.append(
                (
                    student,
                    text,
                )
            )

        for student, text in students:
            response = block.staff_download(
                mock.Mock(params={"student_id": student["item"].student_id})
            )
            self.assertEqual(response.body, text)

        # assert that staff cannot access invalid files
        for student, __ in students:
            with mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
                return_value=block.file_storage_path(  # lint-amnesty
                    "", "test_notfound.txt"
                ),  # lint-amnesty
            ):
                response = block.staff_download(
                    mock.Mock(params={"student_id": student["item"].student_id})
                )
                self.assertEqual(response.status_code, 404)

    def test_download_annotated_unicode_filename(self):
        """
        Tests download annotated assignment
        with filename in unicode for non staff member.
        """
        block = self.make_one()
        fred = self.make_student(block, "fred2")
        with self.dummy_upload("файл.txt") as (upload, expected):
            block.staff_upload_annotated(
                mock.Mock(params={"annotated": upload, "module_id": fred["module"].id})
            )
        self.personalize(block, **fred)
        response = block.download_annotated(None)
        self.assertEqual(response.body, expected)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(  # lint-amnesty
                "", "test_notfound.txt"
            ),  # lint-amnesty
        ):
            response = block.download_annotated(None)
            self.assertEqual(response.status_code, 404)

    def test_staff_download_unicode_filename(self):
        """
        Tests download assignment with filename in unicode for staff.
        """
        block = self.make_one()
        student = self.make_student(block, "fred")
        self.personalize(block, **student)
        with self.dummy_upload("файл.txt") as (upload, expected):
            block.upload_assignment(mock.Mock(params={"assignment": upload}))
        response = block.staff_download(
            mock.Mock(params={"student_id": student["item"].student_id})
        )
        self.assertEqual(response.body, expected)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(  # lint-amnesty
                "", "test_notfound.txt"
            ),  # lint-amnesty
        ):
            response = block.staff_download(
                mock.Mock(params={"student_id": student["item"].student_id})
            )
            self.assertEqual(response.status_code, 404)

    def test_staff_download_filename_with_spaces(self):
        """
        Tests download assignment with spaces in filename.
        """
        file_name = "my assignment 2.txt"
        block = self.make_one()
        student = self.make_student(block, "fred")
        self.personalize(block, **student)
        with self.dummy_upload(file_name) as (upload, expected):
            block.upload_assignment(mock.Mock(params={"assignment": upload}))
        response = block.staff_download(
            mock.Mock(params={"student_id": student["item"].student_id})
        )
        self.assertEqual(response.body, expected)
        assert (
            six.moves.urllib.parse.quote(file_name.encode("utf-8"))
            in response.content_disposition
        )

    @data("my,assignment.txt", "my,1,1,assignment.txt")
    def test_file_download_comma_in_name(self, file_name):
        """
        Tests download assignment with comma in filename.
        """
        block = self.make_one()
        student = self.make_student(block, "fred")
        self.personalize(block, **student)
        with self.dummy_upload(file_name) as (upload, expected):
            block.upload_assignment(mock.Mock(params={"assignment": upload}))
        response = block.staff_download(
            mock.Mock(params={"student_id": student["item"].student_id})
        )
        self.assertEqual(response.body, expected)
        assert (
            six.moves.urllib.parse.quote(file_name.encode("utf-8"))
            in response.content_disposition
        )

    def test_get_staff_grading_data_not_staff(self):
        """
        test staff grading data for non staff members.
        """
        self.runtime.user_is_staff = False
        block = self.make_one()
        with self.assertRaises(PermissionDenied):
            block.get_staff_grading_data(None)

    def test_get_staff_grading_data(self):
        """
        Test fetch grading data for staff members.
        """
        block = self.make_one()
        barney = self.make_student(
            block,
            "barney",
            filename="foo.txt",
            score=10,
            annotated_filename="foo_corrected.txt",
            comment="Good work!",
        )
        fred = self.make_student(block, "fred", filename="bar.txt")
        data = block.get_staff_grading_data(  # lint-amnesty, pylint: disable=redefined-outer-name
            None
        ).json_body
        assignments = sorted(data["assignments"], key=lambda x: x["username"])

        barney_assignment, fred_assignment = assignments

        assert barney_assignment["module_id"] == barney["module"].id
        assert barney_assignment["username"] == "barney"
        assert barney_assignment["fullname"] == "barney"
        assert barney_assignment["filename"] == "foo.txt"
        assert barney_assignment["score"] == 10
        assert barney_assignment["annotated"] == "foo_corrected.txt"
        assert barney_assignment["comment"] == "Good work!"
        assert barney_assignment["approved"] is True
        assert barney_assignment["finalized"] is True
        assert barney_assignment["may_grade"] is False
        assert barney_assignment["needs_approval"] is False
        assert barney_assignment["student_id"] == barney["item"].student_id
        assert barney_assignment["submission_id"] == barney["submission"]["uuid"]
        assert is_near_now(parse_timestamp(barney_assignment["timestamp"]))

        assert fred_assignment["module_id"] == fred["module"].id
        assert fred_assignment["username"] == "fred"
        assert fred_assignment["fullname"] == "fred"
        assert fred_assignment["filename"] == "bar.txt"
        assert fred_assignment["score"] is None
        assert fred_assignment["annotated"] == ""
        assert fred_assignment["comment"] == ""
        assert fred_assignment["approved"] is False
        assert fred_assignment["finalized"] is True
        assert fred_assignment["may_grade"] is True
        assert fred_assignment["needs_approval"] is False
        assert fred_assignment["student_id"] == fred["item"].student_id
        assert fred_assignment["submission_id"] == fred["submission"]["uuid"]
        assert is_near_now(parse_timestamp(fred_assignment["timestamp"]))

    @mock.patch("edx_sga.sga.log")
    def test_assert_logging_when_student_module_created(self, mocked_log):
        """
        Verify logs are created when student modules are created.
        """
        block = self.make_one()
        self.make_student(
            block,
            "tester",
            make_state=False,
            filename="foo.txt",
            score=10,
            annotated_filename="foo_corrected.txt",
            comment="Good work!",
        )
        block.staff_grading_data()
        module_creation_log_message = mocked_log.info.call_args[0]
        self.assertIn("tester", module_creation_log_message)
        self.assertIn(block.course_id, module_creation_log_message)
        self.assertIn(block.location, module_creation_log_message)

    def test_enter_grade_instructor(self):
        """
        Test enter grade by instructors.
        """
        block = self.make_one()
        block.is_instructor = lambda: True
        fred = self.make_student(block, "fred5", filename="foo.txt")
        block.enter_grade(
            mock.Mock(
                params={
                    "module_id": fred["module"].id,
                    "submission_id": fred["submission"]["uuid"],
                    "grade": 9,
                    "comment": "Good!",
                }
            )
        )
        state = json.loads(StudentModule.objects.get(pk=fred["module"].id).state)
        self.assertEqual(state["comment"], "Good!")
        self.assertEqual(block.get_score(fred["item"].student_id), 9)

    def test_enter_grade_staff(self):
        """
        Test grade enter by staff.
        """
        block = self.make_one()
        fred = self.make_student(block, "fred5", filename="foo.txt")
        block.enter_grade(
            mock.Mock(
                params={
                    "module_id": fred["module"].id,
                    "submission_id": fred["submission"]["uuid"],
                    "grade": 9,
                    "comment": "Good!",
                }
            )
        )
        state = json.loads(StudentModule.objects.get(pk=fred["module"].id).state)
        self.assertEqual(state["comment"], "Good!")
        self.assertEqual(state["staff_score"], 9)

    @data(None, "", "9.24", "second")
    def test_enter_grade_fail(self, grade):
        """
        Tests grade enter fail.
        """
        block = self.make_one()
        fred = self.make_student(block, "fred5", filename="foo.txt")
        with mock.patch("edx_sga.sga.log") as mocked_log:
            block.enter_grade(
                mock.Mock(
                    params={
                        "module_id": fred["module"].id,
                        "submission_id": fred["submission"]["uuid"],
                        "grade": grade,
                    }
                )
            )
        mocked_log.error.assert_called_with(
            "enter_grade: invalid grade submitted for course:%s module:%s student:%s",
            block.course_id,
            block.location,
            "fred5",
        )

    def test_remove_grade(self):
        """
        Test remove grade.
        """
        block = self.make_one()
        student = self.make_student(block, "fred6", score=9, comment="Good!")
        module = student["module"]
        item = student["item"]
        request = mock.Mock(
            params={
                "module_id": module.id,
                "student_id": item.student_id,
            }
        )
        block.remove_grade(request)
        state = json.loads(StudentModule.objects.get(pk=module.id).state)
        self.assertEqual(block.get_score(item.student_id), None)
        self.assertEqual(state["comment"], "")

    @data(True, False)
    def test_past_due(self, is_past):
        """
        Test due date is pass.
        """
        block = self.make_one()
        now = datetime.datetime.now(tz=pytz.utc)
        delta = datetime.timedelta(days=-1 if is_past else 1)
        block.due = now + delta
        assert block.past_due() is is_past
        assert block.past_due() is block.is_past_due()

    @data(True, False)
    def test_showanswer(self, is_answer_available):
        """
        The student state should have the solution if answer is available
        """
        block = self.make_one(solution="A solution")
        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.answer_available",
            return_value=is_answer_available,
        ):
            assert block.student_state()["solution"] == (
                "A solution" if is_answer_available else ""
            )

    @data((True, "/static/foo"), (False, "/c4x/foo/bar/asset"))
    @unpack
    def test_replace_url(self, has_static_asset_path, path):
        """
        If the static asset path is set on a course, it should be substituted when the course is rendered
        """
        # make a runtime with a static asset path, which will override the base_asset_url
        if has_static_asset_path:
            self.runtime = self.make_runtime(static_asset_path="foo")
            self.scope_ids = self.make_scope_ids(self.runtime)

        block = self.make_one(
            solution='<a href="/static/test.pdf">A PDF</a>',
            showanswer=ShowAnswer.ALWAYS,
        )
        solution = block.student_state()["solution"]
        assert f'<a href="{path}/test.pdf">A PDF</a>' == solution

    def test_base_asset_url(self):
        """
        The base asset url for the course should be passed to the javascript so it can replace static links
        """
        block = self.make_one(solution="A solution")
        assert block.student_state()["base_asset_url"] == "/c4x/foo/bar/asset/"

    def test_correctness_available(self):
        """
        Correctness should always be available
        """
        block = self.make_one()
        assert block.correctness_available() is True

    def test_has_attempted(self):
        """
        A SGA problem is attempted if they uploaded their submission and it is finalized
        """
        block = self.make_one()
        assert block.has_attempted() is False
        assert block.is_correct() is False
        assert block.can_attempt() is True

        with self.dummy_upload("test.txt") as (upload, _):
            block.upload_assignment(mock.Mock(params={"assignment": upload}))
        assert block.has_attempted() is False
        assert block.is_correct() is False
        assert block.can_attempt() is True

        block.finalize_uploaded_assignment(mock.Mock())
        assert block.has_attempted() is True
        assert block.is_correct() is True
        assert block.can_attempt() is False

    @data(True, False)
    def test_runtime_user_is_staff(self, is_staff):
        course = CourseFactory.create(org="org", number="bar", display_name="baz")
        descriptor = ItemFactory(category="pure", parent=course)

        staff = StaffFactory.create(course_key=course.id)
        self.runtime, _ = render.get_module_system_for_user(
            staff if is_staff else User.objects.create(),
            self.student_data,
            descriptor,
            course.id,
            mock.Mock(),
            mock.Mock(),
            mock.Mock(),
            course=course,
        )
        block = self.make_one()
        assert block.runtime_user_is_staff() is is_staff

    @data(True, False)
    def test_grace_period(self, has_grace_period):
        block = self.make_one()

        # Due date is slightly in the past
        block.due = datetime.datetime.now(tz=pytz.utc) - datetime.timedelta(seconds=500)
        if has_grace_period:
            block.graceperiod = datetime.timedelta(days=1)

        assert block.past_due() is not has_grace_period

    def make_test_vertical(self, solution_attribute=None, solution_element=None):
        """Create a test vertical with an SGA unit inside"""
        solution_attribute = (
            f'solution="{html.escape(solution_attribute)}"'
            if solution_attribute
            else ""
        )
        solution_element = (
            f"<solution>{solution_element}</solution>" if solution_element else ""
        )

        return f"""<vertical display_name="SGA Unit">
              <edx_sga url_name="edx_sga" xblock-family="xblock.v1" display_name="SGA Test 1" {solution_attribute}>
                {solution_element}
              </edx_sga>
            </vertical>"""

    def import_test_course(self, solution_attribute=None, solution_element=None):
        """
        Import the test course with the sga unit
        """
        # adapted from edx-platform/cms/djangoapps/contentstore/management/commands/tests/test_cleanup_assets.py
        root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        input_dir = os.path.join(root, "test_data")

        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir))

        xml_dir = os.path.join(temp_dir, "xml")
        shutil.copytree(input_dir, xml_dir)

        with open(
            os.path.join(xml_dir, "2017_SGA", "vertical", "vertical.xml"), "w"
        ) as f:
            f.write(self.make_test_vertical(solution_attribute, solution_element))

        store = modulestore()
        import_course_from_xml(
            store,
            "sga_user",
            xml_dir,
        )

        return store.get_course(CourseLocator.from_string("SGAU/SGA101/course"))

    @data(
        *[
            ["<p>Broken xml", "<p>You're seeing the answer</p>", "<p>Broken xml"],
            ["<p>Broken xml", None, "<p>Broken xml"],
            [
                None,
                "<p>You're seeing the answer</p>",
                "<p>You're seeing the answer</p>",
            ],
            [None, None, ""],
        ]
    )
    @unpack
    def test_import(
        self, solution_attribute_value, solution_element_value, expected_solution_text
    ):
        """Import the test course with the SGA module"""
        course = self.import_test_course(
            solution_attribute_value, solution_element_value
        )
        sga = (
            course.get_children()[0]
            .get_children()[0]
            .get_children()[0]
            .get_children()[0]
        )
        assert expected_solution_text in sga.solution
        assert sga.showanswer == ShowAnswer.PAST_DUE

    @data(
        *[
            ["<p>Broken xml", "<p>You're seeing the answer</p>", "<p>Broken xml", None],
            ["<p>Broken xml", None, "<p>Broken xml", None],
            [
                None,
                "<p>You're seeing the answer</p>",
                None,
                "<p>You're seeing the answer</p>",
            ],
            [None, None, None, None],
        ]
    )
    @unpack
    def test_export(
        self,
        solution_attribute_value,
        solution_element_value,
        expected_solution_attribute,
        expected_solution_element,
    ):
        """Export the test course with the SGA module"""
        course = self.import_test_course(
            solution_attribute_value, solution_element_value
        )

        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir))

        store = modulestore()
        export_course_to_xml(store, None, course.id, temp_dir, "2017_SGA")

        with open(os.path.join(temp_dir, "2017_SGA", "vertical", "vertical.xml")) as f:
            content = f.read()

        # If both are true the expected output should only have the attribute, since it took precedence
        # and the attribute contents are broken XML
        assert reformat_xml(content) == reformat_xml(
            self.make_test_vertical(
                expected_solution_attribute, expected_solution_element
            )
        )
