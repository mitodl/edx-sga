"""Shared test functionality"""

import hashlib
import shutil
import unittest
from contextlib import contextmanager
from datetime import datetime
from tempfile import mkdtemp
from unittest.mock import Mock

from lxml import etree

import pytz
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from xblock.fields import DateTime


class TempfileMixin(unittest.TestCase):
    """
    Test class that sets up a temp directory for 'uploaded' files, and configures Django's
    default_storage to use that directory
    """

    temp_directory = None
    default_storage = None
    _original_media_root = None
    _original_file_storage = None

    @classmethod
    def set_up_temp_directory(cls):
        """
        Creates a temp directory and fixes Django settings
        """
        cls._original_media_root = settings.MEDIA_ROOT
        cls._original_file_storage = settings.DEFAULT_FILE_STORAGE
        cls.temp_directory = mkdtemp()
        settings.MEDIA_ROOT = cls.temp_directory
        settings.DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
        cls.default_storage = default_storage

    @classmethod
    def tear_down_temp_directory(cls):
        """
        Cleans up temp directory and fixes Django settings
        """
        shutil.rmtree(cls.temp_directory, ignore_errors=True)
        settings.MEDIA_ROOT = cls._original_media_root
        settings.DEFAULT_FILE_STORAGE = cls._original_file_storage
        del cls._original_media_root
        del cls._original_file_storage

    @contextmanager
    def dummy_upload(self, filename, data=b"some information"):
        """
        Provides a temporary file to act as a file that a user has uploaded

        Args:
            filename (str): A filename
            data (bytes): Random string

        Yields:
            (upload, data): The upload object and the data in the file
        """
        try:
            default_storage.save(filename, ContentFile(data))
            with default_storage.open(filename, "rb") as f:
                yield Mock(file=f), data
        finally:
            if default_storage.exists(filename):
                default_storage.delete(filename)

    @contextmanager
    def dummy_file_in_storage(self, rel_file_path):
        """
        Puts an empty file at the given file path (relative to the class temp directory)
        """
        try:
            default_storage.save(rel_file_path, ContentFile(b""))
            yield rel_file_path
        finally:
            if default_storage.exists(rel_file_path):
                default_storage.delete(rel_file_path)


class DummyResource:
    """
    A Resource class for use in tests
    """

    def __init__(self, path):
        self.path = path

    def __eq__(self, other):
        return isinstance(other, DummyResource) and self.path == other.path


def get_sha1(data):
    """
    Helper function to produce a SHA1 hash
    """
    algorithm = hashlib.sha1()
    algorithm.update(data)
    return algorithm.hexdigest()


def is_near_now(other_time):
    """
    Is a time pretty close to right now?
    """
    delta = abs(other_time - datetime.now(tz=pytz.utc))
    return delta.total_seconds() < 5


def parse_timestamp(timestamp):
    """
    Parse the xblock timestamp into a UTC datetime
    """
    return datetime.strptime(timestamp, DateTime.DATETIME_FORMAT).replace(
        tzinfo=pytz.utc
    )


def reformat_xml(xml_string):
    """
    Parse and render the XML to remove whitespace differences
    """
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.XML(xml_string, parser=parser)

    # Remove whitespace
    for elem in root.iter("*"):
        if elem.text is not None:
            elem.text = elem.text.strip()
            if not elem.text:
                elem.text = None

    return etree.tostring(root)
