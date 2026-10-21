"""What Android's Back button does in the app (no Flet here, so it can be tested on its own).

Back goes back one step, in this order (an open sheet is closed by Android before the app is asked):

1. after a jump (Charts › a category › Show transactions; Accounts › an account) it returns to
   where you were, as you left it;
2. on another tab it goes to the Dashboard;
3. on the Dashboard the first Back asks "Press Back again to exit", a second one within
   ``EXIT_WINDOW`` seconds leaves the app.

Changing tabs yourself (tapping the bar or swiping) starts afresh: the jumps before it are forgotten,
so Back from there goes to the Dashboard, as Android's own apps do.
"""

from __future__ import annotations

EXIT_WINDOW = 2.0
"""Seconds in which a second Back on the Dashboard leaves the app."""

RESTORE, DASHBOARD, ASK_EXIT, EXIT = "restore", "dashboard", "ask_exit", "exit"


class BackSteps:
    def __init__(self):
        self._steps: list[dict] = []
        self._asked_at: float | None = None

    def jumped(self, state: dict) -> None:
        """Before a jump to another place: ``state`` is the place left (restored on Back)."""
        self._steps.append(state)
        self._asked_at = None

    def tab_chosen(self) -> None:
        """The person changed tabs: earlier jumps no longer apply."""
        self._steps.clear()
        self._asked_at = None

    @property
    def depth(self) -> int:
        return len(self._steps)

    def back(self, tab: int, now: float) -> tuple[str, dict | None]:
        """What Back does now, on ``tab`` (0 = Dashboard), at time ``now`` (seconds).

        Returns (RESTORE, the state to restore), (DASHBOARD, None), (ASK_EXIT, None) or (EXIT, None).
        """
        if self._steps:
            self._asked_at = None
            return RESTORE, self._steps.pop()
        if tab != 0:
            self._asked_at = None
            return DASHBOARD, None
        if self._asked_at is not None and now - self._asked_at <= EXIT_WINDOW:
            self._asked_at = None
            return EXIT, None
        self._asked_at = now
        return ASK_EXIT, None
