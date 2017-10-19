# -*- coding: utf-8 -*-
"""
Tests for SGA
"""
import datetime
import json
import mimetypes
import unittest
import tempfile
import mock
import pkg_resources
import pytz

from ddt import ddt, data  # pylint: disable=import-error
from django.conf import settings  # lint-amnesty, pylint: disable=import-error
from django.core.exceptions import PermissionDenied
from django.core.files.storage import FileSystemStorage
from opaque_keys.edx.locations import Location  # lint-amnesty, pylint: disable=import-error
from opaque_keys.edx.locator import CourseLocator  # lint-amnesty, pylint: disable=import-error
from xblock.field_data import DictFieldData
from xblock.fields import DateTime

from edx_sga.tests.common import DummyResource, DummyUpload


SHA1 = 'da39a3ee5e6b4b0d3255bfef95601890afd80709'


def fake_get_submission(upload):
    """returns fake submission"""
    return {
        "answer": {
            "sha1": SHA1,
            "filename": upload.file.name.encode('utf-8'),
            "mimetype": mimetypes.guess_type(upload.file.name.encode('utf-8'))[0]
        }
    }


class MockedStudentModule(object):
    """dummy representation of xblock class"""
    def __init__(self):
        self.course_id = CourseLocator(org='foo', course='baz', run='bar')
        self.module_state_key = "foo"
        self.student = mock.Mock(username="fred6", is_staff=False, password="test")
        self.state = '{"display_name": "Staff Graded Assignment"}'

    def save(self):
        """save method do nothing"""


@ddt
class StaffGradedAssignmentMockedTests(unittest.TestCase):
    """
    Create a SGA block with mock data.
    """
    def setUp(self):
        """
        Creates a test course ID, mocks the runtime, and creates a fake storage
        engine for use in all tests
        """
        super(StaffGradedAssignmentMockedTests, self).setUp()
        self.course_id = CourseLocator(org='foo', course='baz', run='bar')
        self.runtime = mock.Mock(anonymous_student_id='MOCK')
        self.scope_ids = mock.Mock()
        tmp = tempfile.mkdtemp()
        patcher = mock.patch(
            "edx_sga.sga.default_storage",
            FileSystemStorage(tmp))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.staff = mock.Mock(return_value={
            "password": "test",
            "username": "tester",
            "is_staff": True
        })

    def make_xblock(self, display_name=None, **kwargs):
        """
        Creates a XBlock SGA for testing purpose.
        """
        from edx_sga.sga import StaffGradedAssignmentXBlock as cls
        field_data = DictFieldData(kwargs)
        block = cls(self.runtime, field_data, self.scope_ids)
        block.location = Location(
            'foo', 'bar', 'baz', 'category', 'name', 'revision'
        )

        block.xmodule_runtime = self.runtime
        block.course_id = self.course_id
        block.scope_ids.usage_id = "i4x://foo/bar/category/name"
        block.category = 'problem'

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
        self.assertEqual(block.max_score(), 20)

    def test_max_score_integer(self):
        """
        Test assigning a float max score is rounded to nearest integer.
        """
        block = self.make_xblock(points=20.4)
        self.assertEqual(block.max_score(), 20)

    def personalize_upload(self, block, upload):
        # pylint: disable=unused-argument
        """
        Set values on block from file upload.
        """
        now = datetime.datetime.utcnow().replace(tzinfo=pytz.timezone(getattr(settings, "TIME_ZONE", pytz.utc.zone)))
        setattr(block, "annotated_mimetype", mimetypes.guess_type(upload.file.name.encode('utf-8'))[0])
        setattr(block, "annotated_filename", upload.file.name.encode('utf-8'))
        setattr(block, "annotated_sha1", SHA1)
        setattr(
            block,
            "annotated_timestamp",
            now.strftime(
                DateTime.DATETIME_FORMAT
            )
        )

    @mock.patch('edx_sga.sga._resource', DummyResource)
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_student_view(self, fragment, render_template):
        # pylint: disable=unused-argument
        """
        Test student view renders correctly.
        """
        block = self.make_xblock("Custom name")

        with mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.get_submission',
            return_value={}
        ), mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.student_state',
            return_value={
                'uploaded': None,
                'annotated': None,
                'upload_allowed': True,
                'max_score': 100,
                'graded': None
            }
        ):
            fragment = block.student_view()
            assert render_template.called is True
            template_arg = render_template.call_args[0][0]
            self.assertEqual(
                template_arg,
                'templates/staff_graded_assignment/show.html'
            )
            context = render_template.call_args[0][1]
            self.assertEqual(context['is_course_staff'], True)
            self.assertEqual(context['id'], 'name')
            student_state = json.loads(context['student_state'])
            self.assertEqual(student_state['uploaded'], None)
            self.assertEqual(student_state['annotated'], None)
            self.assertEqual(student_state['upload_allowed'], True)
            self.assertEqual(student_state['max_score'], 100)
            self.assertEqual(student_state['graded'], None)
            fragment.add_css.assert_called_once_with(
                DummyResource("static/css/edx_sga.css"))
            fragment.initialize_js.assert_called_once_with(
                "StaffGradedAssignmentXBlock")

    @mock.patch('edx_sga.sga._resource', DummyResource)
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.upload_allowed')
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.get_score')
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_student_view_with_score(self, fragment, render_template, get_score, upload_allowed):
        # pylint: disable=unused-argument
        """
        Tests scores are displayed correctly on student view.
        """
        path = pkg_resources.resource_filename(__package__, 'test_sga.py')
        upload = mock.Mock(file=DummyUpload(path, 'foo.txt'))
        block = self.make_xblock()
        get_score.return_value = 10
        upload_allowed.return_value = True
        block.comment = "ok"

        with mock.patch(
            'submissions.api.create_submission',
        ) as mocked_create_submission, mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.student_state', return_value={}
        ):
            block.upload_assignment(mock.Mock(params={'assignment': upload}))
        assert mocked_create_submission.called is True

        with mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.get_submission',
            return_value=fake_get_submission(upload)
        ), mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.student_state',
            return_value={
                'graded': {u'comment': 'ok', u'score': 10},
                'uploaded': {u'filename': u'foo.txt'},
                'max_score': 100
            }
        ):
            fragment = block.student_view()
            assert render_template.called is True
            template_arg = render_template.call_args[0][0]
            self.assertEqual(
                template_arg,
                'templates/staff_graded_assignment/show.html'
            )
            context = render_template.call_args[0][1]
            self.assertEqual(context['is_course_staff'], True)
            self.assertEqual(context['id'], 'name')
            student_state = json.loads(context['student_state'])
            self.assertEqual(student_state['uploaded'], {u'filename': u'foo.txt'})
            self.assertEqual(student_state['graded'], {u'comment': 'ok', u'score': 10})
            self.assertEqual(student_state['max_score'], 100)
            fragment.add_css.assert_called_once_with(
                DummyResource("static/css/edx_sga.css"))
            fragment.initialize_js.assert_called_once_with(
                "StaffGradedAssignmentXBlock")

    @mock.patch('edx_sga.sga._resource', DummyResource)
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_studio_view(self, fragment, render_template):
        # pylint: disable=unused-argument
        """
        Test studio view is displayed correctly.
        """
        block = self.make_xblock()
        fragment = block.studio_view()
        assert render_template.called is True
        template_arg = render_template.call_args[0][0]
        self.assertEqual(
            template_arg,
            'templates/staff_graded_assignment/edit.html'
        )
        cls = type(block)
        context = render_template.call_args[0][1]
        self.assertEqual(tuple(context['fields']), (
            (cls.display_name, 'Staff Graded Assignment', 'string'),
            (cls.points, 100, 'number'),
            (cls.weight, '', 'number')
        ))
        fragment.add_javascript.assert_called_once_with(
            DummyResource("static/js/src/studio.js"))
        fragment.initialize_js.assert_called_once_with(
            "StaffGradedAssignmentXBlock")

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
            block.save_sga(mock.Mock(method="POST", body=json.dumps({
                "display_name": "Test Block",
                "points": '100',
                "weight": -10.0})))
            self.assertEqual(block.weight, orig_weight)

            # Test string weight doesn't work
            block.save_sga(mock.Mock(method="POST", body=json.dumps({
                "display_name": "Test Block",
                "points": '100',
                "weight": "a"})))
            self.assertEqual(block.weight, orig_weight)

        def point_positive_int_test():
            """
            Tests point is positive number.
            """
            # Test negative doesn't work
            block.save_sga(mock.Mock(method="POST", body=json.dumps({
                "display_name": "Test Block",
                "points": '-10',
                "weight": 11})))
            self.assertEqual(block.points, orig_score)

            # Test float doesn't work
            block.save_sga(mock.Mock(method="POST", body=json.dumps({
                "display_name": "Test Block",
                "points": '24.5',
                "weight": 11})))
            self.assertEqual(block.points, orig_score)

        orig_score = 23
        block = self.make_xblock()
        block.save_sga(mock.Mock(body='{}'))
        self.assertEqual(block.display_name, "Staff Graded Assignment")
        self.assertEqual(block.points, 100)
        self.assertEqual(block.weight, None)
        block.save_sga(mock.Mock(method="POST", body=json.dumps({
            "display_name": "Test Block",
            "points": str(orig_score),
            "weight": 11})))
        self.assertEqual(block.display_name, "Test Block")
        self.assertEqual(block.points, orig_score)
        self.assertEqual(block.weight, 11)

        point_positive_int_test()
        weights_positive_float_test()

    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.student_submission_id')
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.upload_allowed')
    @mock.patch('edx_sga.sga._get_sha1')
    def test_upload_download_assignment(self, _get_sha1, upload_allowed, student_submission_id):
        """
        Tests upload and download assignment for non staff.
        """
        path = pkg_resources.resource_filename(__package__, 'test_sga.py')
        expected = open(path, 'rb').read()
        file_name = 'test.txt'
        upload = mock.Mock(file=DummyUpload(path, file_name))
        block = self.make_xblock()
        student_submission_id.return_value = {
            "student_id": 1,
            "course_id": block.block_course_id,
            "item_id": block.block_id,
            "item_type": 'sga',
        }
        upload_allowed.return_value = True

        with mock.patch('submissions.api.create_submission') as mocked_create_submission, mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(SHA1, file_name)
        ), mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.student_state', return_value={}
        ):
            block.upload_assignment(mock.Mock(params={'assignment': upload}))
        assert mocked_create_submission.called is True

        with mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.get_submission',
            return_value=fake_get_submission(upload)
        ), mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(SHA1, file_name)
        ):
            response = block.download_assignment(None)
            self.assertEqual(response.body, expected)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path("", "test_notfound.txt")
        ), mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.get_submission',
            return_value=fake_get_submission(upload)
        ):
            response = block.download_assignment(None)
            self.assertEqual(response.status_code, 404)

    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.get_module_by_id')
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff')
    @mock.patch('edx_sga.sga._get_sha1')
    def test_staff_upload_download_annotated(self, _get_sha1, is_course_staff, get_module_by_id):
        # pylint: disable=no-member
        """
        Tests upload and download of annotated staff files.
        """
        get_module_by_id.return_value = MockedStudentModule()
        is_course_staff.return_value = True
        _get_sha1.return_value = SHA1
        file_name = 'test.txt'
        path = pkg_resources.resource_filename(__package__, 'test_sga.py')
        expected = open(path, 'rb').read()
        upload = mock.Mock(file=DummyUpload(path, file_name))
        block = self.make_xblock()

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.staff_grading_data",
            return_value={}
        ) as staff_grading_data:
            block.staff_upload_annotated(mock.Mock(params={'annotated': upload, 'module_id': 1}))
        assert staff_grading_data.called is True

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(SHA1, file_name)
        ):
            response = block.staff_download_annotated(mock.Mock(params={'module_id': 1}))
            self.assertEqual(response.body, expected)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path("", "test_notfound.txt")
        ):
            response = block.staff_download_annotated(
                mock.Mock(params={'module_id': 1})
            )
            self.assertEqual(response.status_code, 404)

    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.get_module_by_id')
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff')
    @mock.patch('edx_sga.sga._get_sha1')
    def test_download_annotated(self, _get_sha1, is_course_staff, get_module_by_id):
        # pylint: disable=no-member
        """
        Test download annotated assignment for non staff.
        """
        get_module_by_id.return_value = MockedStudentModule()
        is_course_staff.return_value = True
        _get_sha1.return_value = SHA1
        path = pkg_resources.resource_filename(__package__, 'test_sga.py')
        expected = open(path, 'rb').read()
        file_name = 'test.txt'
        upload = mock.Mock(file=DummyUpload(path, file_name))
        block = self.make_xblock()

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.staff_grading_data",
            return_value={}
        ) as staff_grading_data:
            block.staff_upload_annotated(mock.Mock(params={
                'annotated': upload,
                'module_id': 1
            }))
        assert staff_grading_data.called is True
        self.personalize_upload(block, upload)
        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path(SHA1, file_name)
        ):
            response = block.download_annotated(None)
            self.assertEqual(response.body, expected)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path("", "test_notfound.txt")
        ):
            response = block.download_annotated(None)
            self.assertEqual(response.status_code, 404)

    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.upload_allowed')
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.get_module_by_id')
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff')
    @mock.patch('edx_sga.sga._get_sha1')
    def test_staff_download(self, _get_sha1, is_course_staff, get_module_by_id, upload_allowed):
        """
        Test download for staff.
        """
        get_module_by_id.return_value = MockedStudentModule()
        is_course_staff.return_value = True
        upload_allowed.return_value = True
        _get_sha1.return_value = SHA1
        path = pkg_resources.resource_filename(__package__, 'test_sga.py')
        expected = open(path, 'rb').read()
        upload = mock.Mock(file=DummyUpload(path, 'test.txt'))
        block = self.make_xblock()

        with mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.student_state', return_value={}
        ), mock.patch("submissions.api.create_submission") as mocked_create_submission:
            block.upload_assignment(mock.Mock(params={'assignment': upload}))
        assert mocked_create_submission.called is True
        self.personalize_upload(block, upload)

        with mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.get_submission',
            return_value=fake_get_submission(upload)
        ):
            response = block.staff_download(mock.Mock(params={
                'student_id': 1}))
            self.assertEqual(response.body, expected)

        with mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.file_storage_path",
            return_value=block.file_storage_path("", "test_notfound.txt")
        ), mock.patch(
            'edx_sga.sga.StaffGradedAssignmentXBlock.get_submission',
            return_value=fake_get_submission(upload)
        ):
            response = block.staff_download(
                mock.Mock(params={'student_id': 1})
            )
            self.assertEqual(response.status_code, 404)

    def test_get_staff_grading_data_not_staff(self):
        """
        test staff grading data for non staff members.
        """
        self.runtime.user_is_staff = False
        block = self.make_xblock()
        with self.assertRaises(PermissionDenied):
            block.get_staff_grading_data(None)

    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.get_module_by_id')
    def test_enter_grade_instructor(self, get_module_by_id):
        # pylint: disable=no-member
        """
        Test enter grade by instructors.
        """
        get_module_by_id.return_value = MockedStudentModule()
        block = self.make_xblock()
        block.is_instructor = lambda: True
        with mock.patch("submissions.api.set_score") as mocked_set_score, mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.staff_grading_data",
            return_value={}
        ):
            block.enter_grade(
                mock.Mock(
                    params={
                        'module_id': 1,
                        'submission_id': "70be63e7-3fec-4dbf-b39c-1c05a5749410",
                        'grade': 9,
                        'comment': "Good!"
                    }
                )
            )
        mocked_set_score.assert_called_with(
            "70be63e7-3fec-4dbf-b39c-1c05a5749410",
            9,
            block.max_score()
        )

    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.get_module_by_id')
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff')
    def test_enter_grade_staff(self, is_course_staff, get_module_by_id):
        # pylint: disable=no-member
        """
        Test grade enter by staff.
        """
        is_course_staff.return_value = True
        module = MockedStudentModule()
        get_module_by_id.return_value = module
        block = self.make_xblock()
        with mock.patch("edx_sga.sga.log") as mocked_log, mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.staff_grading_data",
            return_value={}
        ):
            block.enter_grade(mock.Mock(params={
                'module_id': 1,
                'submission_id': "70be63e7-3fec-4dbf-b39c-1c05a5749410",
                'grade': 9,
                'comment': "Good!"}))
        mocked_log.info.assert_called_with(
            "enter_grade for course:%s module:%s student:%s",
            block.course_id,
            "foo",
            module.student.username
        )

    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.get_module_by_id')
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff')
    @data(None, "", '9.24', "second")
    def test_enter_grade_fail(self, grade, is_course_staff, get_module_by_id):
        # pylint: disable=no-member
        """
        Tests grade enter fail.
        """
        is_course_staff.return_value = True
        module = MockedStudentModule()
        get_module_by_id.return_value = module
        block = self.make_xblock()
        with mock.patch('edx_sga.sga.log') as mocked_log, mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.staff_grading_data",
            return_value={}
        ):
            block.enter_grade(mock.Mock(params={
                'module_id': 1,
                'submission_id': '70be63e7-3fec-4dbf-b39c-1c05a5749410',
                'grade': grade
            }))
        mocked_log.error.assert_called_with(
            "enter_grade: invalid grade submitted for course:%s module:%s student:%s",
            block.course_id,
            block.location,
            module.student.username
        )

    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.get_module_by_id')
    @mock.patch('edx_sga.sga.StaffGradedAssignmentXBlock.is_course_staff')
    def test_remove_grade(self, is_course_staff, get_module_by_id):
        # pylint: disable=no-member
        """
        Test remove grade.
        """
        block = self.make_xblock()
        is_course_staff.return_value = True
        get_module_by_id.return_value = MockedStudentModule()
        request = mock.Mock(params={
            'module_id': 1,
            'student_id': 1,
        })
        with mock.patch("submissions.api.reset_score") as mocked_reset_score, mock.patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock.staff_grading_data",
            return_value={}
        ):
            block.remove_grade(request)

        mocked_reset_score.assert_called_with(
            1,
            unicode(block.course_id),
            unicode(block.block_id)
        )
