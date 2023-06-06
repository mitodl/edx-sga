"""Constants"""

BLOCK_SIZE = 2 ** 10 * 8  # 8kb
ITEM_TYPE = "sga"
ATTR_KEY_ANONYMOUS_USER_ID = 'edx-platform.anonymous_user_id'
ATTR_KEY_USER_IS_STAFF = 'edx-platform.user_is_staff'
ATTR_KEY_USER_ROLE = 'edx-platform.user_role'


class ShowAnswer:
    """
    Constants for when to show answer
    """

    ALWAYS = "always"
    ANSWERED = "answered"
    ATTEMPTED = "attempted"
    CLOSED = "closed"
    FINISHED = "finished"
    CORRECT_OR_PAST_DUE = "correct_or_past_due"
    PAST_DUE = "past_due"
    NEVER = "never"
