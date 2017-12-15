"""shared test data"""
from contextlib import contextmanager
import os
import shutil
from tempfile import mkdtemp

from mock import Mock


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
