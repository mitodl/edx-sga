"""Constants"""

BLOCK_SIZE = 2 ** 10 * 8  # 8kb
ITEM_TYPE = "sga"


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
