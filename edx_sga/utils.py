"""
Utility functions for the SGA XBlock
"""
import datetime
import hashlib
import os
import time
from functools import partial

import pytz
from django.conf import settings
from django.core.files.storage import default_storage as django_default_storage, get_storage_class
from edx_sga.constants import BLOCK_SIZE


def get_default_storage():
    """
    Get config for storage from settings, use Django's default_storage if no such settings are defined
    """
    # .. setting_name: SGA_STORAGE_SETTINGS
    # .. setting_default: {}
    # .. setting_description: Specifies the storage class and keyword arguments to use in the constructor
    #    Default storage will be used if this settings in not specified.
    # .. setting_example: {
    #        STORAGE_CLASS: 'storage',
    #        STORAGE_KWARGS: {}
    #    }
    sga_storage_settings = getattr(settings, "SGA_STORAGE_SETTINGS", None)

    if sga_storage_settings:
        return get_storage_class(
            sga_storage_settings['STORAGE_CLASS']
        )(**sga_storage_settings['STORAGE_KWARGS'])

    # If settings not defined, use default_storage from Django
    return django_default_storage

default_storage = get_default_storage()

def utcnow():
    """
    Get current date and time in UTC
    """
    return datetime.datetime.now(tz=pytz.utc)


def is_finalized_submission(submission_data):
    """
    Helper function to determine whether or not a Submission was finalized by the student
    """
    if submission_data and submission_data.get("answer") is not None:
        return submission_data["answer"].get("finalized", True)
    return False


def get_file_modified_time_utc(file_path):
    """
    Gets the UTC timezone-aware modified time of a file at the given file path
    """
    file_timezone = (
        # time.tzname returns a 2 element tuple:
        #   (local non-DST timezone, e.g.: 'EST', local DST timezone, e.g.: 'EDT')
        pytz.timezone(time.tzname[0])
        if settings.DEFAULT_FILE_STORAGE
        == "django.core.files.storage.FileSystemStorage"
        else pytz.utc
    )

    file_time = default_storage.get_modified_time(file_path)

    if file_time.tzinfo is None:
        return file_timezone.localize(file_time).astimezone(pytz.utc)
    else:
        return file_time.astimezone(pytz.utc)


def get_sha1(file_descriptor):
    """
    Get file hex digest (fingerprint).
    """
    sha1 = hashlib.sha1()
    for block in iter(partial(file_descriptor.read, BLOCK_SIZE), b""):
        sha1.update(block)
    file_descriptor.seek(0)
    return sha1.hexdigest()


def get_file_storage_path(locator, file_hash, original_filename):
    """
    Returns the file path for an uploaded SGA submission file
    """
    return "{loc.org}/{loc.course}/{loc.block_type}/{loc.block_id}/{file_hash}{ext}".format(
        loc=locator, file_hash=file_hash, ext=os.path.splitext(original_filename)[1]
    )


def file_contents_iter(file_path):
    """
    Returns an iterator over the contents of a file located at the given file path
    """
    file_descriptor = default_storage.open(file_path)
    return iter(partial(file_descriptor.read, BLOCK_SIZE), b"")
