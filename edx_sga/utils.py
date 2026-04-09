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
from django.core.files.storage import FileSystemStorage
from django.core.files.storage import default_storage as django_default_storage
from django.core.files.storage import storages
from django.utils.module_loading import import_string
from edx_sga.constants import BLOCK_SIZE


def get_default_storage():
    """
    Return the configured SGA file storage backend, using this priority:
    1. Django ≥4.2 `STORAGES` registry:
       - If `settings.STORAGES["sga_storage"]` exists, returns that storage instance.


    2. Legacy `SGA_STORAGE_SETTINGS` dict:
       {
           "STORAGE_CLASS": "<dotted.path.to.StorageClass>",
           "STORAGE_KWARGS": { ... },
       }
       If present, imports and instantiates that class with the given kwargs.

    3. As a final fallback, returns Django’s shared `default_storage` singleton.

    This ensures:
      • Forward compatibility with the new `STORAGES`-based configuration.
      • Backward compatibility with old `SGA_STORAGE_SETTINGS`.
      • No breakage if neither setting is defined.
    """
    # .. setting_name: SGA_STORAGE_SETTINGS
    # .. setting_default: {}
    # .. setting_description: Specifies the storage class and keyword arguments to use in the constructor
    #    Default storage will be used if this settings in not specified.
    # .. setting_example: {
    #        STORAGE_CLASS: 'storage',
    #        STORAGE_KWARGS: {}
    #    }
    # Priority 1: Django 5's STORAGES config
    storages_config = getattr(settings, 'STORAGES', {})
    if "sga_storage" in storages_config:
        return storages["sga_storage"]

    # Priority 2: Legacy config (backward compatibility)
    sga_storage_settings = getattr(settings, 'SGA_STORAGE_SETTINGS', None)
    if sga_storage_settings:
        return import_string(
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
        if isinstance(default_storage, FileSystemStorage)
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
