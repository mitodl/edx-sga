"""shared test data"""
import os


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
