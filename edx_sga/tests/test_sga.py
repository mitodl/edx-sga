"""
Tests for SGA
"""
# pylint: disable=imported-auth-user
import builtins
import datetime
import json
import mimetypes
import os
import uuid
from unittest import mock

import pytest
import pytz
from ddt import data, ddt, unpack
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.timezone import now as django_now
from opaque_keys.edx.locations import Location
from opaque_keys.edx.locator import CourseLocator
from workbench.runtime import WorkbenchRuntime
from xblock.field_data import DictFieldData
from xblock.fields import DateTime

from edx_sga.tests.common import DummyResource, TempfileMixin


SHA1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
UUID = "8c4b765745f746f7a128470842211601"


pytestmark = pytest.mark.django_db


def fake_get_submission(**kwargs):
    """returns fake submission data"""
    answer = {
        "sha1": SHA1,
        "filename": kwargs.get("filename", "file.txt"),
        "mimetype": kwargs.get("mimetype", "mime/type"),
    }
    if kwargs.get("finalized"):
        answer["finalized"] = kwargs.get("finalized")
    return {
        "answer": answer,
        "uuid": UUID,
        "submitted_at": kwargs.get("submitted_at", None),
    }


def fake_upload_submission(upload):
    """returns fake submission data with values calculated from an upload object"""
    return fake_get_submission(
        filename=upload.file.name, mimetype=mimetypes.guess_type(upload.file.name)[0]
    )


def fake_student_module():
    """dummy representation of xblock class"""
    return mock.Mock(
        course_id=CourseLocator(org="foo", course="baz", run="bar"),
        module_state_key="foo",
        student=mock.Mock(username="fred6", is_staff=False, password="test"),
        state='{"display_name": "Staff Graded Assignment"}',
        save=mock.Mock(),
    )


class FakeWorkbenchRuntime(WorkbenchRuntime):
    """Override for testing purposes"""

    anonymous_student_id = "MOCK"
    user_is_staff = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        User.objects.create(username=self.anonymous_student_id)

    def get_real_user(self, username):
        """Get the real user"""
        return User.objects.get(username=username)


@ddt
class StaffGradedAssignmentMockedTests(TempfileMixin):
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

        # fakes imports
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            """mock imported object if not it is not available"""
            try:
                return real_import(name, *args, **kwargs)
            except ImportError:
                for module in ("common", "courseware", "lms", "xmodule"):
                    if name.startswith(f"{module}.") or name == module:
                        return mock.Mock()
                if name == "safe_lxml":
                    return real_import("lxml", *args, **kwargs)
                raise

        builtins.__import__ = fake_import

        def restore_import():
            """restore builtin importer"""
            builtins.__import__ = real_import

        self.addCleanup(restore_import)

        self.course_id = CourseLocator(org="foo", course="baz", run="bar")
        self.runtime = FakeWorkbenchRuntime()
        self.scope_ids = mock.Mock()
        self.staff = mock.Mock(
            return_value={"password": "test", "username": "tester", "is_staff": True}
        )

    def make_xblock(self, display_name=None, **kwargs):
        """
        Creates a XBlock SGA for testing purpose.
        """
        from edx_sga.sga import (  # pylint: disable=import-outside-toplevel
            StaffGradedAssignmentXBlock as cls,
        )

        field_data = DictFieldData(kwargs)
        block = cls(self.runtime, field_data, self.scope_ids)
        block.location = Location("foo", "bar", "baz", "category", "name", "revision")

        block.xmodule_runtime = self.runtime
        block.course_id = self.course_id
        block.scope_ids.usage_id = "i4x://foo/bar/category/name"
        block.category = "problem"

        if display_name:
            block.display_name = display_name

        block.start = datetime.datetime(2010, 5, 12, 2, 42, tzinfo=pytz.utc)
        return block

    def test_ctor(self):
        """
        Test points are set correctly.
        """
        block = self.make_xblock(points=10)
        assert block.display_name == "Staff Graded Assignment"
        assert block.points == 10

    def test_max_score(self):
        """
        Text max score is set correctly.
        """
        block = self.make_xblock(points=20)
        assert block.max_score() == 20

    def test_max_score_integer(self):
        """
        Test assigning a float max score is rounded to nearest integer.
        """
        block = self.make_xblock(points=20.4)
        assert block.max_score() == 20

    def personalize_upload(self, block, upload):
        """
        Set values on block from file upload.
        """
        now = datetime.datetime.utcnow().replace(
            tzinfo=pytz.timezone(getattr(settings, "TIME_ZONE", pytz.utc.zone))
        )
        block.annotated_mimetype = mimetypes.guess_type(upload.file.name)[0]
        block.annotated_filename = upload.file.name.encode("utf-8")
        block.annotated_sha1 = SHA1
        block.annotated_timestamp = now.strftime(DateTime.DATETIME_FORMAT)

    @mock.patch("edx_sga.sga._resource", DummyResource)
    @mock.patch("edx_sga.sga.render_template")
    @mock.patch("edx_sga.sga.Fragment")
    def test_student_view(self, fragment, render_template):
        """
        Test student view renders correctly.
        """
        block = self.make_xblock("Custom name")

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_submission", return_value={}
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.student_state",
            return_value={
                "uploaded": None,
                "annotated": None,
                "upload_allowed": True,
                "max_score": 100,
                "graded": None,
            },
        ):
            fragment = block.student_view()
            assert render_template.called is True
            template_arg = render_template.call_args[0][0]
            assert template_arg == "templates/staff_graded_assignment/show.html"
            context = render_template.call_args[0][1]
            assert context["is_course_staff"] is True
            assert context["id"] == "name"
            student_state = json.loads(context["student_state"])
            assert student_state["uploaded"] is None
            assert student_state["annotated"] is None
            assert student_state["upload_allowed"] is True
            assert student_state["max_score"] == 100
            assert student_state["graded"] is None
            # pylint: disable=no-member
            fragment.add_css.assert_called_once_with(
                DummyResource("static/css/edx_sga.css")
            )
            fragment.initialize_js.assert_called_once_with(
                "StaffGradedAssignmentXBlock"
            )

    @mock.patch("edx_sga.sga._resource", DummyResource)
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.upload_allowed")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.get_score")
    @mock.patch("edx_sga.sga.render_template")
    @mock.patch("edx_sga.sga.Fragment")
    def test_student_view_with_score(
        self, fragment, render_template, get_score, upload_allowed
    ):
        """
        Tests scores are displayed correctly on student view.
        """
        block = self.make_xblock()
        get_score.return_value = 10
        upload_allowed.return_value = True
        block.comment = "ok"

        with self.dummy_upload("foo.txt") as (upload, _):
            with mock.patch(
                "submissions.api.create_submission",
            ) as mocked_create_submission, mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.student_state", return_value={}
            ), mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.get_or_create_student_module",
                return_value=fake_student_module(),
            ):
                block.upload_assignment(mock.Mock(params={"assignment": upload}))
            assert mocked_create_submission.called is True

            with mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.get_submission",
                return_value=fake_upload_submission(upload),
            ), mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.student_state",
                return_value={
                    "graded": {"comment": "ok", "score": 10},
                    "uploaded": {"filename": "foo.txt"},
                    "max_score": 100,
                },
            ):
                fragment = block.student_view()
                assert render_template.called is True
                template_arg = render_template.call_args[0][0]
                assert template_arg == "templates/staff_graded_assignment/show.html"
                context = render_template.call_args[0][1]
                assert context["is_course_staff"] is True
                assert context["id"] == "name"
                student_state = json.loads(context["student_state"])
                assert student_state["uploaded"] == {"filename": "foo.txt"}
                assert student_state["graded"] == {"comment": "ok", "score": 10}
                assert student_state["max_score"] == 100
                # pylint: disable=no-member
                fragment.add_css.assert_called_once_with(
                    DummyResource("static/css/edx_sga.css")
                )
                fragment.initialize_js.assert_called_once_with(
                    "StaffGradedAssignmentXBlock"
                )

    def test_studio_view(self):
        """
        Test studio view is using the StudioEditableXBlockMixin function
        """
        with mock.patch(
            "edx_sga.sga.StudioEditableXBlockMixin.studio_view"
        ) as studio_view_mock:
            block = self.make_xblock()
            block.studio_view()
        studio_view_mock.assert_called_once_with(None)

    def test_save_sga(self):
        """
        Tests save SGA  block on studio
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
                    ).encode("utf-8"),
                )
            )
            assert block.weight == orig_weight

            # Test string weight doesn't work
            block.save_sga(
                mock.Mock(
                    method="POST",
                    body=json.dumps(
                        {"display_name": "Test Block", "points": "100", "weight": "a"}
                    ).encode("utf-8"),
                )
            )
            assert block.weight == orig_weight

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
                    ).encode("utf-8"),
                )
            )
            assert block.points == orig_score

            # Test float doesn't work
            block.save_sga(
                mock.Mock(
                    method="POST",
                    body=json.dumps(
                        {"display_name": "Test Block", "points": "24.5", "weight": 11}
                    ).encode("utf-8"),
                )
            )
            assert block.points == orig_score

        orig_score = 23
        block = self.make_xblock()
        block.save_sga(mock.Mock(body="{}"))
        assert block.display_name == "Staff Graded Assignment"
        assert block.points == 100
        assert block.weight is None
        block.save_sga(
            mock.Mock(
                method="POST",
                body=json.dumps(
                    {"display_name": "Test Block", "points": orig_score, "weight": 11}
                ).encode("utf-8"),
            )
        )
        assert block.display_name == "Test Block"
        assert block.points == orig_score
        assert block.weight == 11

        point_positive_int_test()
        weights_positive_float_test()

    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.get_student_item_dict")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.upload_allowed")
    @mock.patch("edx_sga.sga.get_sha1")
    def test_upload_download_assignment(
        self, get_sha1, upload_allowed, get_student_item_dict
    ):
        # pylint: disable=unused-argument
        """
        Tests upload and download assignment for non staff.
        """
        file_name = "test.txt"
        block = self.make_xblock()
        get_student_item_dict.return_value = {
            "student_id": 1,
            "course_id": block.block_course_id,
            "item_id": block.block_id,
            "item_type": "sga",
        }
        upload_allowed.return_value = True

        with self.dummy_upload(file_name) as (upload, expected):
            with mock.patch(
                "submissions.api.create_submission"
            ) as mocked_create_submission, mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
                return_value=block.file_storage_path(SHA1, file_name),
            ), mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.student_state", return_value={}
            ), mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.get_or_create_student_module",
                return_value=fake_student_module(),
            ) as mocked_create_student_module:
                block.upload_assignment(mock.Mock(params={"assignment": upload}))
            assert mocked_create_submission.called is True
            assert mocked_create_student_module.called is True

            with mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.get_submission",
                return_value=fake_upload_submission(upload),
            ), mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
                return_value=block.file_storage_path(SHA1, file_name),
            ):
                response = block.download_assignment(None)
                assert response.body == expected

            with mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
                return_value=block.file_storage_path("", "test_notfound.txt"),
            ), mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.get_submission",
                return_value=fake_upload_submission(upload),
            ):
                response = block.download_assignment(None)
                assert response.status_code == 404

    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.get_student_item_dict")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.upload_allowed")
    @data(({"finalized": False}, True), ({}, True), ({"finalized": True}, False))
    @unpack
    def test_finalize_uploaded_assignment(
        self,
        finalized_setting,
        model_change_expected,
        upload_allowed,
        get_student_item_dict,
    ):
        """
        Tests that finalize_uploaded_assignment sets a submission to be finalized
        """
        block = self.make_xblock()
        get_student_item_dict.return_value = {
            "student_id": 1,
            "course_id": block.block_course_id,
            "item_id": block.block_id,
            "item_type": "sga",
        }
        upload_allowed.return_value = True
        existing_submitted_at_value = django_now()
        fake_submission_data = fake_get_submission(**finalized_setting)
        fake_submission_object = mock.Mock(
            submitted_at=existing_submitted_at_value,
            answer=fake_submission_data["answer"],
        )

        with mock.patch(
            "edx_sga.sga.Submission.objects.get", return_value=fake_submission_object
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_submission",
            return_value=fake_submission_data,
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.student_state", return_value={}
        ):
            block.finalize_uploaded_assignment(mock.Mock())

        assert fake_submission_object.answer["finalized"] is True
        assert (
            existing_submitted_at_value != fake_submission_object.submitted_at
        ) is model_change_expected
        assert fake_submission_object.save.called is model_change_expected

    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.get_student_module")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff")
    @mock.patch("edx_sga.sga.get_sha1")
    def test_staff_upload_download_annotated(
        self, get_sha1, is_course_staff, get_student_module
    ):
        """
        Tests upload and download of annotated staff files.
        """
        get_student_module.return_value = fake_student_module()
        is_course_staff.return_value = True
        get_sha1.return_value = SHA1
        file_name = "test.txt"
        block = self.make_xblock()

        with self.dummy_upload(file_name) as (upload, expected), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.staff_grading_data",
            return_value={},
        ) as staff_grading_data:
            block.staff_upload_annotated(
                mock.Mock(params={"annotated": upload, "module_id": 1})
            )
        assert staff_grading_data.called is True

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(SHA1, file_name),
        ):
            response = block.staff_download_annotated(
                mock.Mock(params={"module_id": 1})
            )
            assert response.body == expected

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path("", "test_notfound.txt"),
        ):
            response = block.staff_download_annotated(
                mock.Mock(params={"module_id": 1})
            )
            assert response.status_code == 404

    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.get_student_module")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff")
    @mock.patch("edx_sga.sga.get_sha1")
    def test_download_annotated(self, get_sha1, is_course_staff, get_student_module):
        """
        Test download annotated assignment for non staff.
        """
        get_student_module.return_value = fake_student_module()
        is_course_staff.return_value = True
        get_sha1.return_value = SHA1

        file_name = "test.txt"
        block = self.make_xblock()

        with self.dummy_upload(file_name) as (upload, expected):
            with mock.patch(
                "edx_sga.sga.StaffGradedAssignmentXBlock.staff_grading_data",
                return_value={},
            ) as staff_grading_data:
                block.staff_upload_annotated(
                    mock.Mock(params={"annotated": upload, "module_id": 1})
                )
            assert staff_grading_data.called is True
            self.personalize_upload(block, upload)
        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(SHA1, file_name),
        ):
            response = block.download_annotated(None)
            assert response.body == expected

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path("", "test_notfound.txt"),
        ):
            response = block.download_annotated(None)
            assert response.status_code == 404

    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.upload_allowed")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.get_student_module")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff")
    @mock.patch("edx_sga.sga.get_sha1")
    def test_staff_download(
        self, get_sha1, is_course_staff, get_student_module, upload_allowed
    ):
        """
        Test download for staff.
        """
        get_student_module.return_value = fake_student_module()
        is_course_staff.return_value = True
        upload_allowed.return_value = True
        get_sha1.return_value = SHA1
        block = self.make_xblock()

        with self.dummy_upload("test.txt") as (upload, expected), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.student_state", return_value={}
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_or_create_student_module",
            return_value=fake_student_module(),
        ), mock.patch(
            "submissions.api.create_submission"
        ) as mocked_create_submission:
            block.upload_assignment(mock.Mock(params={"assignment": upload}))
        assert mocked_create_submission.called is True
        self.personalize_upload(block, upload)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_submission",
            return_value=fake_upload_submission(upload),
        ):
            response = block.staff_download(mock.Mock(params={"student_id": 1}))
            assert response.body == expected

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path("", "test_notfound.txt"),
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_submission",
            return_value=fake_upload_submission(upload),
        ):
            response = block.staff_download(mock.Mock(params={"student_id": 1}))
            assert response.status_code == 404

    @unpack
    @data(
        {
            "past_due": False,
            "score": None,
            "is_finalized_submission": False,
            "expected_value": True,
        },
        {
            "past_due": True,
            "score": None,
            "is_finalized_submission": False,
            "expected_value": False,
        },
        {
            "past_due": False,
            "score": 80,
            "is_finalized_submission": False,
            "expected_value": False,
        },
        {
            "past_due": False,
            "score": None,
            "is_finalized_submission": True,
            "expected_value": False,
        },
    )
    def test_upload_allowed(
        self, past_due, score, is_finalized_submission, expected_value
    ):
        """
        Tests that upload_allowed returns the right value under certain conditions
        """
        block = self.make_xblock()
        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.past_due", return_value=past_due
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_score", return_value=score
        ), mock.patch(
            "edx_sga.sga.is_finalized_submission", return_value=is_finalized_submission
        ):
            assert block.upload_allowed(submission_data={}) is expected_value

    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.count_archive_files")
    @mock.patch("edx_sga.sga.zip_student_submissions")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.get_sorted_submissions")
    @data((False, False), (True, True))
    @unpack
    def test_prepare_download_submissions(
        self,
        is_zip_file_available,
        downloadable,
        get_sorted_submissions,
        zip_student_submissions,
        count_archive_files,
    ):
        """
        Test prepare download api
        """
        block = self.make_xblock()
        count_archive_files.return_value = 2
        get_sorted_submissions.return_value = [
            {
                "submission_id": uuid.uuid4().hex,
                "filename": f"test_{uuid.uuid4().hex}.txt",
                "timestamp": datetime.datetime.now(tz=pytz.utc),
            }
            for __ in range(2)
        ]
        zip_student_submissions.delay = mock.Mock()
        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.is_zip_file_available",
            return_value=is_zip_file_available,
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_real_user",
            return_value=self.staff,
        ), mock.patch(
            "edx_sga.utils.default_storage.get_modified_time",
            return_value=datetime.datetime.now(),
        ):
            response = block.prepare_download_submissions(None)
            response_body = json.loads(response.body.decode("utf-8"))
            assert response_body["downloadable"] is downloadable

    @mock.patch("edx_sga.sga.get_file_modified_time_utc")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.count_archive_files")
    @mock.patch("edx_sga.sga.zip_student_submissions")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.get_sorted_submissions")
    @data((2, True, False), (1, False, True))
    @unpack
    def test_prepare_download_submissions_when_student_score_reset(
        self,
        count_archive_files,
        downloadable,
        zip_task_called,
        get_sorted_submissions,
        zip_student_submissions,
        count_archive_files_mock,
        get_file_modified_time_utc,
    ):
        """
        Test prepare download api
        """
        now = datetime.datetime.now(tz=pytz.utc)
        block = self.make_xblock()
        count_archive_files_mock.return_value = count_archive_files
        get_sorted_submissions.return_value = [
            {
                "submission_id": uuid.uuid4().hex,
                "filename": f"test_{uuid.uuid4().hex}.txt",
                "timestamp": now,
            }
            for __ in range(2)
        ]
        get_file_modified_time_utc.return_value = now
        zip_student_submissions.delay = mock.Mock()
        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.is_zip_file_available",
            return_value=True,
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_real_user",
            return_value=self.staff,
        ), mock.patch(
            "edx_sga.utils.default_storage.get_modified_time",
            return_value=datetime.datetime.now(),
        ):
            response = block.prepare_download_submissions(None)
            response_body = json.loads(response.body.decode("utf-8"))
            assert response_body["downloadable"] is downloadable
            assert zip_student_submissions.delay.called is zip_task_called

    @mock.patch("edx_sga.sga.zip_student_submissions")
    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.get_sorted_submissions")
    def test_prepare_download_submissions_task_called(
        self, get_sorted_submissions, zip_student_submissions
    ):
        """
        Test prepare download api
        """
        block = self.make_xblock()
        get_sorted_submissions.return_value = [
            {
                "submission_id": uuid.uuid4().hex,
                "filename": f"test_{uuid.uuid4().hex}.txt",
                "timestamp": datetime.datetime.utcnow(),
            }
            for __ in range(2)
        ]
        zip_student_submissions.delay = mock.Mock()
        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.is_zip_file_available",
            return_value=False,
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_real_user",
            return_value=self.staff,
        ), mock.patch(
            "edx_sga.sga.default_storage.get_modified_time",
            return_value=datetime.datetime.now(),
        ):
            response = block.prepare_download_submissions(None)
            response_body = json.loads(response.body.decode("utf-8"))
            assert response_body["downloadable"] is False

        zip_student_submissions.delay.assert_called_once_with(
            str(block.block_course_id),
            str(block.block_id),
            str(block.location),
            self.staff.username,
        )

    @data((False, False), (True, True))
    @unpack
    def test_download_submissions_status(self, is_zip_file_available, downloadable):
        """test download_submissions_status api"""
        block = self.make_xblock()
        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.is_zip_file_available",
            return_value=is_zip_file_available,
        ):
            response = block.download_submissions_status(None)
            response_body = json.loads(response.body.decode("utf-8"))
            assert response_body["zip_available"] is downloadable

    @mock.patch("edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff")
    def test_download_submissions(self, is_course_staff):
        """tests download_submissions"""
        block = self.make_xblock()
        is_course_staff.return_value = True

        expected = b"some information blah"
        filename = "foo.zip"
        path = os.path.join(self.temp_directory, filename)
        with open(path, "wb") as temp_file:
            temp_file.write(expected)

        with mock.patch("edx_sga.sga.get_zip_file_path", return_value=path), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.get_real_user",
            return_value=self.staff,
        ), mock.patch("edx_sga.sga.get_zip_file_name", return_value=filename):
            response = block.download_submissions(None)
            assert response.status_code == 200
            assert response.body == expected

    def test_clear_student_state(self):
        """Tests that a student's state in the given problem is properly cleared"""
        block = self.make_xblock()
        orig_file_name = "test.txt"
        fake_submission = fake_get_submission(filename=orig_file_name)
        uploaded_file_path = block.file_storage_path(SHA1, orig_file_name)

        with self.dummy_file_in_storage(uploaded_file_path) as file_path:
            with mock.patch(
                "edx_sga.sga.submissions_api.get_submissions",
                return_value=[fake_submission],
            ) as mocked_get_submissions, mock.patch(
                "edx_sga.sga.submissions_api.reset_score"
            ) as mocked_reset_score:
                assert self.default_storage.exists(file_path) is True
                block.clear_student_state(user_id=123)
                assert mocked_get_submissions.called is True
                # Clearing the student state should call 'reset_score' in the submission API,
                # which effectively resets the Submission record.
                assert mocked_reset_score.called is True
                # Clearing the student state should also delete the uploaded file
                assert self.default_storage.exists(file_path) is False
