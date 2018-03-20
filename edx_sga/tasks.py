"""celery async tasks"""
import zipfile
import hashlib
import logging
import os
import tempfile

from django.core.files.storage import default_storage  # lint-amnesty, pylint: disable=import-error

from lms import CELERY_APP  # pylint: disable=no-name-in-module, import-error
from submissions import api as submissions_api  # lint-amnesty, pylint: disable=import-error
from student.models import user_by_anonymous_id  # lint-amnesty, pylint: disable=import-error
from opaque_keys.edx.locator import BlockUsageLocator

from edx_sga.utils import get_file_storage_path
from edx_sga.constants import ITEM_TYPE


log = logging.getLogger(__name__)


def _get_student_submissions(block_id, course_id, locator):
    """
    Returns valid submission file paths with the username of the student that submitted them.

    Args:
        course_id (unicode): edx course id
        block_id (unicode): edx block id
        locator (BlockUsageLocator): BlockUsageLocator for the sga module

    Returns:
        list(tuple): A list of 2-element tuples - (student username, submission file path)
    """
    submissions = submissions_api.get_all_submissions(
        course_id,
        block_id,
        ITEM_TYPE
    )
    return [
        (
            user_by_anonymous_id(submission['student_id']).username,
            get_file_storage_path(
                locator,
                submission['answer']['sha1'],
                submission['answer']['filename']
            )
        )
        for submission in submissions if submission['answer']
    ]


def _compress_student_submissions(zip_file_path, block_id, course_id, locator):
    """
    Creates a zip file of all student submissions for some course

    Args:
        destination_path (str): path (including name) of folder/file which we want to compress.
    """
    student_submissions = _get_student_submissions(block_id, course_id, locator)
    if not student_submissions:
        return

    log.info("Compressing %d student submissions to path: %s ", len(student_submissions), zip_file_path)
    # Build the zip file in memory using temporary file.
    with tempfile.TemporaryFile() as tmp:
        with zipfile.ZipFile(tmp, 'w', compression=zipfile.ZIP_DEFLATED) as zip_pointer:
            for student_username, submission_file_path in student_submissions:
                log.info(
                    "Creating zip file for student: %s, submission path: %s ",
                    student_username,
                    submission_file_path
                )
                with default_storage.open(submission_file_path, 'rb') as destination_file:
                    filename_in_zip = '{}_{}'.format(
                        student_username,
                        os.path.basename(submission_file_path)
                    )
                    zip_pointer.writestr(filename_in_zip, destination_file.read())
        # Reset file pointer
        tmp.seek(0)
        # Write the bytes of the in-memory zip file to an actual file
        log.info(
            "Moving zip file from memory to storage at path: %s ", zip_file_path
        )
        default_storage.save(zip_file_path, tmp)


@CELERY_APP.task
def zip_student_submissions(course_id, block_id, locator_unicode, username):
    """
    Task to download all submissions as zip file

    Args:
        course_id (unicode): edx course id
        block_id (unicode): edx block id
        locator_unicode (unicode): Unicode representing a BlockUsageLocator for the sga module
        username (unicode): user name of the staff user requesting the zip file
    """
    locator = BlockUsageLocator.from_string(locator_unicode)
    zip_file_path = get_zip_file_path(username, course_id, block_id, locator)
    log.info("Creating zip file for course: %s at path: %s", locator, zip_file_path)
    if default_storage.exists(zip_file_path):
        log.info("Deleting already-existing zip file at path: %s", zip_file_path)
        default_storage.delete(zip_file_path)
    _compress_student_submissions(
        zip_file_path,
        block_id,
        course_id,
        locator
    )


def get_zip_file_dir(locator):
    """
    Returns the relative directory path where we are saving the zipped submissions file.

    Args:
        locator (BlockUsageLocator): BlockUsageLocator for the sga module
    """
    return "{loc.org}/{loc.course}/{loc.block_type}_zipped".format(loc=locator)


def get_zip_file_name(username, course_id, block_id):
    """
    Returns the filename and extension of a submission zip file given a username and some
    information about the course.

    Args:
        username (unicode): staff user name
        course_id (unicode): edx course id
        block_id (unicode): edx block id
    """
    return "{username}_submissions_{id}_{course_key}.zip".format(
        username=username,
        id=hashlib.md5(block_id).hexdigest(),
        course_key=course_id
    )


def get_zip_file_path(username, course_id, block_id, locator):
    """
    Returns the relative file path of a submission zip file given a username and some
    information about the course.

    Args:
        username (unicode): user name
        course_id (unicode): edx course id
        block_id (unicode): edx block id
        locator (BlockUsageLocator): BlockUsageLocator for the sga module
    """
    return os.path.join(
        get_zip_file_dir(locator),
        get_zip_file_name(username, course_id, block_id)
    )
