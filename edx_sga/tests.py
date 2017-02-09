# -*- coding: utf-8 -*-
"""
Tests for SGA
"""
import datetime
from ddt import ddt, data
import json
import mock
import os
import pkg_resources
import pytz
import tempfile
from mock import patch

from courseware.models import StudentModule
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.files.storage import FileSystemStorage
from submissions import api as submissions_api
from submissions.models import StudentItem
from student.models import anonymous_id_for_user, UserProfile
from student.tests.factories import AdminFactory
from xblock.field_data import DictFieldData
from xmodule.modulestore.tests.factories import CourseFactory
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from opaque_keys.edx.locations import Location


class DummyResource(object):
    """
     A Resource class for use in tests
    """
    def __init__(self, path):
        self.path = path

    def __eq__(self, other):
        return isinstance(other, DummyResource) and self.path == other.path


class DummyUpload(object):
    """
    Upload and read file.
    """
    def __init__(self, path, name):
        self.stream = open(path, 'rb')
        self.name = name
        self.size = os.path.getsize(path)

    def read(self, number_of_bytes=None):
        """
        Read data from file.
        """
        return self.stream.read(number_of_bytes)

    def seek(self, offset):
        """
        Move to specified byte location in file
        """
        return self.stream.seek(offset)


@ddt
class StaffGradedAssignmentXblockTests(ModuleStoreTestCase):
    """
    Create a SGA block with mock data.
    """
    def setUp(self):
        """
        Creates a test course ID, mocks the runtime, and creates a fake storage
        engine for use in all tests
        """
        super(StaffGradedAssignmentXblockTests, self).setUp()
        course = CourseFactory.create(org='foo', number='bar', display_name='baz')
        self.course_id = course.id
        self.runtime = mock.Mock(anonymous_student_id='MOCK')
        self.scope_ids = mock.Mock()
        tmp = tempfile.mkdtemp()
        patcher = mock.patch(
            "edx_sga.sga.default_storage",
            FileSystemStorage(tmp))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.staff = AdminFactory.create(password="test")

    def make_one(self, display_name=None, **kw):
        """
        Creates a XBlock SGA for testing purpose.
        """
        from edx_sga.sga import StaffGradedAssignmentXBlock as cls
        field_data = DictFieldData(kw)
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
        modulestore().create_item(
            self.staff.username, block.location.course_key, block.location.block_type, block.location.block_id
        )
        return block

    def make_student(self, block, name, make_state=True, **state):
        """
        Create a student along with submission state.
        """
        answer = {}
        module = None
        for key in ('sha1', 'mimetype', 'filename'):
            if key in state:
                answer[key] = state.pop(key)
        score = state.pop('score', None)

        user = User(username=name)
        user.save()
        profile = UserProfile(user=user, name=name)
        profile.save()
        if make_state:
            module = StudentModule(
                module_state_key=block.location,
                student=user,
                course_id=self.course_id,
                state=json.dumps(state))
            module.save()

        anonymous_id = anonymous_id_for_user(user, self.course_id)
        item = StudentItem(
            student_id=anonymous_id,
            course_id=self.course_id,
            item_id=block.block_id,
            item_type='sga')
        item.save()

        if answer:
            student_id = block.student_submission_id(anonymous_id)
            submission = submissions_api.create_submission(student_id, answer)
            if score is not None:
                submissions_api.set_score(
                    submission['uuid'], score, block.max_score())
        else:
            submission = None

        self.addCleanup(item.delete)
        self.addCleanup(profile.delete)
        self.addCleanup(user.delete)

        if make_state:
            self.addCleanup(module.delete)
            return {
                'module': module,
                'item': item,
                'submission': submission
            }

        return {
            'item': item,
            'submission': submission
        }

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

    @mock.patch('edx_sga.sga._resource', DummyResource)
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_student_view(self, fragment, render_template):
        # pylint: disable=unused-argument
        """
        Test student view renders correctly.
        """
        block = self.make_one("Custom name")
        self.personalize(block, **self.make_student(block, 'fred'))
        fragment = block.student_view()
        render_template.assert_called_once()
        template_arg = render_template.call_args[0][0]
        self.assertEqual(
            template_arg,
            'templates/staff_graded_assignment/show.html'
        )
        context = render_template.call_args[0][1]
        self.assertEqual(context['is_course_staff'], True)
        self.assertEqual(context['id'], 'name')
        student_state = json.loads(context['student_state'])
        self.assertEqual(
            student_state['display_name'],
            "Custom name"
        )
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
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_student_view_with_upload(self, fragment, render_template):
        # pylint: disable=unused-argument
        """
        Test student is able to upload assignment correctly.
        """
        block = self.make_one()
        self.personalize(block, **self.make_student(
            block, 'fred"', sha1='foo', filename='foo.bar'))
        block.student_view()
        context = render_template.call_args[0][1]
        student_state = json.loads(context['student_state'])
        self.assertEqual(student_state['uploaded'], {'filename': 'foo.bar'})

    @mock.patch('edx_sga.sga._resource', DummyResource)
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_student_view_with_annotated(self, fragment, render_template):
        # pylint: disable=unused-argument
        """
        Test student view shows annotated files correctly.
        """
        block = self.make_one(
            annotated_sha1='foo', annotated_filename='foo.bar')
        self.personalize(block, **self.make_student(block, "fred"))
        block.student_view()
        context = render_template.call_args[0][1]
        student_state = json.loads(context['student_state'])
        self.assertEqual(student_state['annotated'], {'filename': 'foo.bar'})

    @mock.patch('edx_sga.sga._resource', DummyResource)
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_student_view_with_score(self, fragment, render_template):
        # pylint: disable=unused-argument
        """
        Tests scores are displayed correctly on student view.
        """
        block = self.make_one()
        self.personalize(block, **self.make_student(
            block, 'fred', filename='foo.txt', score=10))
        fragment = block.student_view()
        render_template.assert_called_once()
        template_arg = render_template.call_args[0][0]
        self.assertEqual(
            template_arg,
            'templates/staff_graded_assignment/show.html'
        )
        context = render_template.call_args[0][1]
        self.assertEqual(context['is_course_staff'], True)
        self.assertEqual(context['id'], 'name')
        student_state = json.loads(context['student_state'])
        self.assertEqual(
            student_state['display_name'],
            "Staff Graded Assignment"
        )
        self.assertEqual(student_state['uploaded'], {u'filename': u'foo.txt'})
        self.assertEqual(student_state['annotated'], None)
        self.assertEqual(student_state['upload_allowed'], False)
        self.assertEqual(student_state['max_score'], 100)
        self.assertEqual(student_state['graded'],
                         {u'comment': '', u'score': 10})
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
        block = self.make_one()
        fragment = block.studio_view()
        render_template.assert_called_once()
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
        block = self.make_one()
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

    def test_upload_download_assignment(self):
        """
        Tests upload and download assignment for non staff.
        """
        path = pkg_resources.resource_filename(__package__, 'tests.py')
        expected = open(path, 'rb').read()
        upload = mock.Mock(file=DummyUpload(path, 'test.txt'))
        block = self.make_one()
        self.personalize(block, **self.make_student(block, "fred"))
        block.upload_assignment(mock.Mock(params={'assignment': upload}))
        response = block.download_assignment(None)
        self.assertEqual(response.body, expected)

        with patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock._file_storage_path",
            return_value=block._file_storage_path("", "test_notfound.txt")
        ):
            response = block.download_assignment(None)
            self.assertEqual(response.status_code, 404)

    def test_staff_upload_download_annotated(self):
        # pylint: disable=no-member
        """
        Tests upload and download of annotated staff files.
        """
        path = pkg_resources.resource_filename(__package__, 'tests.py')
        expected = open(path, 'rb').read()
        upload = mock.Mock(file=DummyUpload(path, 'test.txt'))
        block = self.make_one()
        fred = self.make_student(block, "fred1")['module']
        block.staff_upload_annotated(mock.Mock(params={
            'annotated': upload,
            'module_id': fred.id}))
        response = block.staff_download_annotated(mock.Mock(params={
            'module_id': fred.id}))
        self.assertEqual(response.body, expected)

        with patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock._file_storage_path",
            return_value=block._file_storage_path("", "test_notfound.txt")
        ):
            response = block.staff_download_annotated(mock.Mock(params={
            'module_id': fred.id}))
            self.assertEqual(response.status_code, 404)

    def test_download_annotated(self):
        # pylint: disable=no-member
        """
        Test download annotated assignment for non staff.
        """
        path = pkg_resources.resource_filename(__package__, 'tests.py')
        expected = open(path, 'rb').read()
        upload = mock.Mock(file=DummyUpload(path, 'test.txt'))
        block = self.make_one()
        fred = self.make_student(block, "fred2")
        block.staff_upload_annotated(mock.Mock(params={
            'annotated': upload,
            'module_id': fred['module'].id}))
        self.personalize(block, **fred)
        response = block.download_annotated(None)
        self.assertEqual(response.body, expected)

        with patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock._file_storage_path",
            return_value=block._file_storage_path("", "test_notfound.txt")
        ):
            response = block.download_annotated(None)
            self.assertEqual(response.status_code, 404)

    def test_staff_download(self):
        """
        Test download for staff.
        """
        path = pkg_resources.resource_filename(__package__, 'tests.py')
        expected = open(path, 'rb').read()
        upload = mock.Mock(file=DummyUpload(path, 'test.txt'))
        block = self.make_one()
        student = self.make_student(block, 'fred')
        self.personalize(block, **student)
        block.upload_assignment(mock.Mock(params={'assignment': upload}))
        response = block.staff_download(mock.Mock(params={
            'student_id': student['item'].student_id}))
        self.assertEqual(response.body, expected)

        with patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock._file_storage_path",
            return_value=block._file_storage_path("", "test_notfound.txt")
        ):
            response = block.staff_download(mock.Mock(params={
            'student_id': student['item'].student_id}))
            self.assertEqual(response.status_code, 404)

    def test_download_annotated_unicode_filename(self):
        """
        Tests download annotated assignment
        with filename in unicode for non staff member.
        """
        path = pkg_resources.resource_filename(__package__, 'tests.py')
        expected = open(path, 'rb').read()
        upload = mock.Mock(file=DummyUpload(path, 'файл.txt'))
        block = self.make_one()
        fred = self.make_student(block, "fred2")
        block.staff_upload_annotated(mock.Mock(params={
            'annotated': upload,
            'module_id': fred['module'].id}))
        self.personalize(block, **fred)
        response = block.download_annotated(None)
        self.assertEqual(response.body, expected)

        with patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock._file_storage_path",
            return_value=block._file_storage_path("", "test_notfound.txt")
        ):
            response = block.download_annotated(None)
            self.assertEqual(response.status_code, 404)

    def test_staff_download_unicode_filename(self):
        """
        Tests download assignment with filename in unicode for staff.
        """
        path = pkg_resources.resource_filename(__package__, 'tests.py')
        expected = open(path, 'rb').read()
        upload = mock.Mock(file=DummyUpload(path, 'файл.txt'))
        block = self.make_one()
        student = self.make_student(block, 'fred')
        self.personalize(block, **student)
        block.upload_assignment(mock.Mock(params={'assignment': upload}))
        response = block.staff_download(mock.Mock(params={
            'student_id': student['item'].student_id}))
        self.assertEqual(response.body, expected)
        with patch(
            "edx_sga.sga.StaffGradedAssignmentXBlock._file_storage_path",
            return_value=block._file_storage_path("", "test_notfound.txt")
        ):
            response = block.staff_download(mock.Mock(params={
            'student_id': student['item'].student_id}))
            self.assertEqual(response.status_code, 404)

    def test_get_staff_grading_data_not_staff(self):
        """
        test staff grading data for non staff members.
        """
        self.runtime.user_is_staff = False
        block = self.make_one()
        with self.assertRaises(PermissionDenied):
            block.get_staff_grading_data(None)

    def test_get_staff_grading_data(self):
        # pylint: disable=no-member
        """
        Test fetch grading data for staff members.
        """
        block = self.make_one()
        barney = self.make_student(
            block, "barney",
            filename="foo.txt",
            score=10,
            annotated_filename="foo_corrected.txt",
            comment="Good work!")['module']
        fred = self.make_student(
            block, "fred",
            filename="bar.txt")['module']
        data = block.get_staff_grading_data(None).json_body
        assignments = sorted(data['assignments'], key=lambda x: x['username'])
        self.assertEqual(assignments[0]['module_id'], barney.id)
        self.assertEqual(assignments[0]['username'], 'barney')
        self.assertEqual(assignments[0]['fullname'], 'barney')
        self.assertEqual(assignments[0]['filename'], 'foo.txt')
        self.assertEqual(assignments[0]['score'], 10)
        self.assertEqual(assignments[0]['annotated'], 'foo_corrected.txt')
        self.assertEqual(assignments[0]['comment'], 'Good work!')

        self.assertEqual(assignments[1]['module_id'], fred.id)
        self.assertEqual(assignments[1]['username'], 'fred')
        self.assertEqual(assignments[1]['fullname'], 'fred')
        self.assertEqual(assignments[1]['filename'], 'bar.txt')
        self.assertEqual(assignments[1]['score'], None)
        self.assertEqual(assignments[1]['annotated'], None)
        self.assertEqual(assignments[1]['comment'], u'')

    @mock.patch('edx_sga.sga.log')
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
            comment="Good work!"
        )
        block.staff_grading_data()
        mocked_log.info.assert_called_with(
            "Init for course:%s module:%s student:%s  ",
            block.course_id,
            block.location,
            'tester'
        )

    def test_enter_grade_instructor(self):
        # pylint: disable=no-member
        """
        Test enter grade by instructors.
        """
        block = self.make_one()
        block.is_instructor = lambda: True
        fred = self.make_student(block, "fred5", filename='foo.txt')
        block.enter_grade(mock.Mock(params={
            'module_id': fred['module'].id,
            'submission_id': fred['submission']['uuid'],
            'grade': 9,
            'comment': "Good!"}))
        state = json.loads(StudentModule.objects.get(
            pk=fred['module'].id).state)
        self.assertEqual(state['comment'], 'Good!')
        self.assertEqual(block.get_score(fred['item'].student_id), 9)

    def test_enter_grade_staff(self):
        # pylint: disable=no-member
        """
        Test grade enter by staff.
        """
        block = self.make_one()
        fred = self.make_student(block, "fred5", filename='foo.txt')
        block.enter_grade(mock.Mock(params={
            'module_id': fred['module'].id,
            'submission_id': fred['submission']['uuid'],
            'grade': 9,
            'comment': "Good!"}))
        state = json.loads(StudentModule.objects.get(
            pk=fred['module'].id).state)
        self.assertEqual(state['comment'], 'Good!')
        self.assertEqual(state['staff_score'], 9)

    @data(None, "", '9.24', "second")
    def test_enter_grade_fail(self, grade):
        # pylint: disable=no-member
        """
        Tests grade enter fail.
        """
        block = self.make_one()
        fred = self.make_student(block, "fred5", filename='foo.txt')
        with patch('edx_sga.sga.log') as mocked_log:
            block.enter_grade(mock.Mock(params={
                'module_id': fred['module'].id,
                'submission_id': fred['submission']['uuid'],
                'grade': grade}
            ))
        mocked_log.error.assert_called_with(
            "enter_grade: invalid grade submitted for course:%s module:%s student:%s",
            block.course_id,
            block.location,
            "fred5"
        )

    def test_remove_grade(self):
        # pylint: disable=no-member
        """
        Test remove grade.
        """
        block = self.make_one()
        student = self.make_student(
            block, "fred6", score=9, comment='Good!')
        module = student['module']
        item = student['item']
        request = mock.Mock(params={
            'module_id': module.id,
            'student_id': item.student_id,
        })
        block.remove_grade(request)
        state = json.loads(StudentModule.objects.get(pk=module.id).state)
        self.assertEqual(block.get_score(item.student_id), None)
        self.assertEqual(state['comment'], '')

    def test_past_due(self):
        """
        Test due date is pass.
        """
        block = self.make_one()
        block.due = datetime.datetime(2010, 5, 12, 2, 42, tzinfo=pytz.utc)
        self.assertTrue(block.past_due())
