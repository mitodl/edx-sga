"""shared test data"""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import os
import shutil
from tempfile import mkdtemp

from mock import Mock
import pytz
from xblock.fields import DateTime


class DummyResource(object):
    """
     A Resource class for use in tests
    """
    def __init__(self, path):
        self.path = path

    def __eq__(self, other):
        return isinstance(other, DummyResource) and self.path == other.path


@contextmanager
def dummy_upload(filename):
    """
    Provide a mocked upload parameter

    Args:
        filename (str): A filename

    Yields:
        (upload, data): The upload object and the data in the file
    """
    data = b"some information"

    directory = mkdtemp()

    try:
        path = os.path.join(directory, filename)
        with open(path, "wb") as f:
            f.write(data)
        with open(path, "rb") as f:
            yield Mock(file=f), data
    finally:
        shutil.rmtree(directory)


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
