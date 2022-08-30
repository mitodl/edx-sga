"""
Tests for SGA utility functions
"""
import pytest
import pytz

from edx_sga.tests.common import is_near_now
from edx_sga.utils import is_finalized_submission, utcnow


@pytest.mark.parametrize(
    "submission_data,expected_value",
    [
        ({"answer": {"finalized": True}}, True),
        ({"answer": {"filename": "file.txt"}}, True),
        ({"answer": {}}, True),
        ({"answer": {"finalized": False}}, False),
        ({"answer": None}, False),
        ({}, False),
    ],
)
def test_is_finalized_submission(submission_data, expected_value):
    """Test for is_finalized_submission"""
    assert is_finalized_submission(submission_data) is expected_value


def test_utcnow():
    """
    tznow should return a datetime object in UTC
    """
    now = utcnow()
    assert is_near_now(now)
    assert now.tzinfo.zone == pytz.utc.zone
