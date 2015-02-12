import datetime
import json
import mock
import os
import pkg_resources
import pytz
import tempfile
import unittest

from courseware.models import StudentModule
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.files.storage import FileSystemStorage
from submissions import api as submissions_api
from submissions.models import StudentItem
from student.models import anonymous_id_for_user, UserProfile
from xblock.field_data import DictFieldData
from opaque_keys.edx.locations import Location, SlashSeparatedCourseKey


class DummyResource(object):

    def __init__(self, path):
        self.path = path

    def __eq__(self, other):
        return isinstance(other, DummyResource) and self.path == other.path


class DummyUpload(object):

    def __init__(self, path, name):
        self.stream = open(path, 'rb')
        self.name = name
        self.size = os.path.getsize(path)

    def read(self, n=None):
        return self.stream.read(n)

    def seek(self, n):
        return self.stream.seek(n)


class StaffGradedAssignmentXblockTests(unittest.TestCase):

    def setUp(self):
        self.course_id = SlashSeparatedCourseKey.from_deprecated_string(
            'foo/bar/baz'
        )
        self.runtime = mock.Mock(anonymous_student_id='MOCK')
        self.scope_ids = mock.Mock()
        tmp = tempfile.mkdtemp()
        patcher = mock.patch(
            "edx_sga.sga.default_storage",
            FileSystemStorage(tmp))
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_one(self, **kw):
        from edx_sga.sga import StaffGradedAssignmentXBlock as cls
        field_data = DictFieldData(kw)
        block = cls(self.runtime, field_data, self.scope_ids)
        block.location = Location(
            'org', 'course', 'run', 'category', 'name', 'revision'
        )
        block.xmodule_runtime = self.runtime
        block.course_id = self.course_id
        block.scope_ids.usage_id = 'XXX'
        block.category = 'problem'
        block.start = datetime.datetime(2010, 5, 12, 2, 42, tzinfo=pytz.utc)
        return block

    def make_student(self, block, name, **state):
        answer = {}
        for key in ('sha1', 'mimetype', 'filename'):
            if key in state:
                answer[key] = state.pop(key)
        score = state.pop('score', None)

        user = User(username=name)
        user.save()
        profile = UserProfile(user=user, name=name)
        profile.save()
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
        self.addCleanup(module.delete)
        self.addCleanup(user.delete)

        return {
            'module': module,
            'item': item,
            'submission': submission,
        }

    def personalize(self, block, module, item, submission):
        student_module = StudentModule.objects.get(pk=module.id)
        state = json.loads(student_module.state)
        for k, v in state.items():
            setattr(block, k, v)
        self.runtime.anonymous_student_id = item.student_id

    def test_ctor(self):
        block = self.make_one(points=10)
        self.assertEqual(block.display_name, "Staff Graded Assignment")
        self.assertEqual(block.points, 10)

    def test_max_score(self):
        block = self.make_one(points=20)
        self.assertEqual(block.max_score(), 20)

    def test_max_score_integer(self):
        block = self.make_one(points=20.4)
        self.assertEqual(block.max_score(), 20)

    @mock.patch('edx_sga.sga._resource', DummyResource)
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_student_view(self, Fragment, render_template):
        block = self.make_one()
        self.personalize(block, **self.make_student(block, 'fred'))
        fragment = block.student_view()
        render_template.assert_called_once
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
        fragment.add_javascript.assert_called_once_with(
            DummyResource("static/js/src/edx_sga.js"))
        fragment.initialize_js.assert_called_once_with(
            "StaffGradedAssignmentXBlock")

    @mock.patch('edx_sga.sga._resource', DummyResource)
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_student_view_with_upload(self, Fragment, render_template):
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
    def test_student_view_with_annotated(self, Fragment, render_template):
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
    def test_student_view_with_score(self, Fragment, render_template):
        block = self.make_one()
        self.personalize(block, **self.make_student(
            block, 'fred', filename='foo.txt', score=10))
        fragment = block.student_view()
        render_template.assert_called_once
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
        self.assertEqual(student_state['annotated'], None)
        self.assertEqual(student_state['upload_allowed'], False)
        self.assertEqual(student_state['max_score'], 100)
        self.assertEqual(student_state['graded'],
                         {u'comment': '', u'score': 10})
        fragment.add_css.assert_called_once_with(
            DummyResource("static/css/edx_sga.css"))
        fragment.add_javascript.assert_called_once_with(
            DummyResource("static/js/src/edx_sga.js"))
        fragment.initialize_js.assert_called_once_with(
            "StaffGradedAssignmentXBlock")

    @mock.patch('edx_sga.sga._resource', DummyResource)
    @mock.patch('edx_sga.sga.render_template')
    @mock.patch('edx_sga.sga.Fragment')
    def test_studio_view(self, Fragment, render_template):
        block = self.make_one()
        fragment = block.studio_view()
        render_template.assert_called_once
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

    def test_upload_download_assignment(self):
        path = pkg_resources.resource_filename(__package__, 'tests.py')
        expected = open(path, 'rb').read()
        upload = mock.Mock(file=DummyUpload(path, 'test.txt'))
        block = self.make_one()
        self.personalize(block, **self.make_student(block, "fred"))
        block.upload_assignment(mock.Mock(params={'assignment': upload}))
        response = block.download_assignment(None)
        self.assertEqual(response.body, expected)

    def test_staff_upload_download_annotated(self):
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

    def test_download_annotated(self):
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

    def test_staff_download(self):
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

    def test_get_staff_grading_data_not_staff(self):
        self.runtime.user_is_staff = False
        block = self.make_one()
        with self.assertRaises(PermissionDenied):
            block.get_staff_grading_data(None)

    def test_get_staff_grading_data(self):
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

    def test_enter_grade_instructor(self):
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

    def test_enter_grade_float(self):
        block = self.make_one()
        fred = self.make_student(block, "fred5", filename='foo.txt')
        with self.assertRaises(ValueError):
            block.enter_grade(mock.Mock(params={
                'module_id': fred['module'].id,
                'submission_id': fred['submission']['uuid'],
                'grade': '9.24'}))

    def test_remove_grade(self):
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
        block = self.make_one()
        block.due = datetime.datetime(2010, 5, 12, 2, 42, tzinfo=pytz.utc)
        self.assertTrue(block.past_due())
