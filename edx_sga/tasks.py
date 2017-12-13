"""celery async tasks"""
import hashlib
import logging
import os
from shutil import make_archive, rmtree
import six

from django.conf import settings
from django.core.files.storage import default_storage  # lint-amnesty, pylint: disable=import-error

from lms import CELERY_APP  # pylint: disable=no-name-in-module, import-error
from submissions import api as submissions_api  # lint-amnesty, pylint: disable=import-error
from student.models import user_by_anonymous_id  # lint-amnesty, pylint: disable=import-error

log = logging.getLogger(__name__)
DATA_DIR = getattr(settings, "DATA_DIR", "/edx/app/edxapp/data")


def _rm_file(path):
    """
    Removes file if it exist.

    Args:
        path (str): path of new directory
    """
    if os.path.exists(path):
        rmtree(path)


def _collect_student_submissions(block_id, course_id, location, destination_path):
    """
    prepare files for download

    Args:
        course_id (unicode): edx course id
        block_id (unicode): edx block id
        location (Location): location of sga module
        destination_path (str): folder from where we will zip files and facilitate for download
    """
    from edx_sga.sga import BLOCK_SIZE, ITEM_TYPE

    submissions = submissions_api.get_all_submissions(
        course_id,
        block_id,
        ITEM_TYPE
    )
    for submission in submissions:
        answer = submission['answer']
        if answer:
            student = user_by_anonymous_id(submission['student_id'])
            source_file = six.u('{loc.org}/{loc.course}/{loc.block_type}/{loc.block_id}/{sha1}{ext}').format(
                loc=location,
                sha1=answer['sha1'],
                ext=os.path.splitext(answer['filename'])[1]
            )

            destination_file = os.path.join(
                destination_path,
                "{student_name}_{sha1}{ext}".format(
                    student_name=student.username,
                    sha1=answer['sha1'],
                    ext=os.path.splitext(answer['filename'])[1]
                )
            )
            try:
                file_descriptor = default_storage.open(source_file)
                with open(destination_file, 'wb') as file_pointer:
                    while True:
                        data = file_descriptor.read(BLOCK_SIZE)
                        if data == '':  # end of file reached
                            break
                        file_pointer.write(data)

            except IOError:
                log.exception("Unable to download submission of student=%s", student.username)


def _compress_folder(destination_path):
    """
    compress given folder/file

    Args:
        destination_path (str): path (including name) of folder/file which we want to compress.
    """
    make_archive(
        destination_path,
        'zip',
        destination_path
    )


def _get_submissions_base_name(user_name, block_id, course_id):
    """
    returns submission folder name where we are saving files.

    Args:
        course_id (unicode): edx course id
        block_id (unicode): edx block id
        user_name (unicode): staff user name
    """
    return "{username}_submissions_{id}_{course_key}".format(
        username=user_name,
        id=hashlib.md5(block_id).hexdigest(),
        course_key=course_id
    )


def _get_dir_path(submissions_dir_name, location=None):
    """
    returns directory path where we are saving files.

    Args:
        submissions_dir_name (str): name of folder
        location (Location): location of sga module
    """
    if location:
        return os.path.join(
            DATA_DIR,
            "{loc.org}/{loc.course}/{loc.run}/{submissions_dir_name}".format(
                loc=location,
                submissions_dir_name=submissions_dir_name
            )
        )

    return os.path.join(DATA_DIR, submissions_dir_name)


def _remove_existing_artifacts(destination_path):
    """
    removes existing submission collection folder and zip file.

    Args:
        destination_path (str): folder from where we will zip files and facilitate for download
    """
    _rm_file(destination_path)
    _rm_file("{}.zip".format(destination_path))  # remove existing zip file


@CELERY_APP.task
def zip_student_submissions(course_id, block_id, location, user):
    """
    Task to download all submissions as zip file

    Args:
        course_id (unicode): edx course id
        block_id (unicode): edx block id
        location (Location): location of sga module
        user_name (str): staff user name
    """
    submissions_dir_name = _get_submissions_base_name(user.username, block_id, course_id)
    destination_path = _get_dir_path(submissions_dir_name, location)
    _remove_existing_artifacts(destination_path)
    os.mkdir(destination_path)
    _collect_student_submissions(block_id, course_id, location, destination_path)
    _compress_folder(destination_path)


def get_zip_file_name(user_name, block_id, course_id):
    """
    returns submission folder name where we are saving files temporary.

    Args:
        course_id (unicode): edx course id
        block_id (unicode): edx block id
        user_name (unicode): staff user name
    """
    submissions_dir_name = _get_submissions_base_name(user_name, block_id, course_id)
    return "{}.zip".format(submissions_dir_name)


def get_zip_file_path(username, course_id, block_id, location):
    """
    returns zip file path.

    Args:
        username (unicode): user name
        course_id (unicode): edx course id
        block_id (unicode): edx block id
        location (Location): location of sga module
    """
    return _get_dir_path(
        get_zip_file_name(
            username,
            block_id,
            course_id
        ),
        location
    )
