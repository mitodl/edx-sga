"""XBlock mixins for showanswer"""

import logging

from django.utils.translation import gettext_lazy as _
from xblock.fields import Scope, String

from edx_sga.constants import ShowAnswer

log = logging.getLogger(__name__)


class ShowAnswerXBlockMixin:
    """
    Mixin for showanswer functionality
    """

    showanswer = String(
        display_name=_("Show Answer"),
        help=_(
            "Defines when to show the answer to the problem. "
            "A default value can be set in Advanced Settings."
        ),
        scope=Scope.settings,
        default=ShowAnswer.PAST_DUE,  # Default to PAST_DUE instead of FINISHED for backwards compat
        values=[
            {"display_name": _("Always"), "value": ShowAnswer.ALWAYS},
            {"display_name": _("Answered"), "value": ShowAnswer.ANSWERED},
            {"display_name": _("Attempted"), "value": ShowAnswer.ATTEMPTED},
            {"display_name": _("Closed"), "value": ShowAnswer.CLOSED},
            {"display_name": _("Finished"), "value": ShowAnswer.FINISHED},
            {
                "display_name": _("Correct or Past Due"),
                "value": ShowAnswer.CORRECT_OR_PAST_DUE,
            },
            {"display_name": _("Past Due"), "value": ShowAnswer.PAST_DUE},
            {"display_name": _("Never"), "value": ShowAnswer.NEVER},
        ],
    )
    solution = String(
        help=_("Solution to the problem to show to the user"),
        display_name=_("Solution"),
        scope=Scope.settings,
        multiline_editor="html",
        resettable_editor=False,
        default="",
    )

    def answer_available(self):  # pylint: disable=too-many-return-statements
        """
        Is the user allowed to see an answer?
        """
        if not self.correctness_available():
            # If correctness is being withheld, then don't show answers either.
            return False
        elif self.showanswer == "":
            return False
        elif self.showanswer == ShowAnswer.NEVER:
            return False
        elif self.runtime_user_is_staff():
            # This is after the 'never' check because admins can see the answer
            # unless the problem explicitly prevents it
            return True
        elif self.showanswer == ShowAnswer.ATTEMPTED:
            return self.has_attempted()
        elif self.showanswer == ShowAnswer.ANSWERED:
            return self.is_correct()
        elif self.showanswer == ShowAnswer.CLOSED:
            return self.closed()
        elif self.showanswer == ShowAnswer.FINISHED:
            return self.closed() or self.is_correct()
        elif self.showanswer == ShowAnswer.CORRECT_OR_PAST_DUE:
            return self.is_correct() or self.is_past_due()
        elif self.showanswer == ShowAnswer.PAST_DUE:
            return self.is_past_due()
        elif self.showanswer == ShowAnswer.ALWAYS:
            return True

        return False

    def closed(self):
        """
        Is the student still allowed to submit answers?
        """
        return not self.can_attempt() or self.is_past_due()

    def correctness_available(self):
        """
        Is the user allowed to see whether she's answered correctly?
        Limits access to the correct/incorrect flags, messages, and problem score.
        """
        raise NotImplementedError

    def is_past_due(self):
        """
        Is it now past this problem's due date, including grace period?
        """
        raise NotImplementedError

    def is_correct(self):
        """
        True iff full points
        """
        raise NotImplementedError

    def has_attempted(self):
        """
        True if the student has already attempted this problem
        """
        raise NotImplementedError

    def can_attempt(self):
        """
        True if the student is allowed to attempt the problem again
        """
        raise NotImplementedError

    def runtime_user_is_staff(self):
        """
        Is the current user a staff user?
        """
        raise NotImplementedError
