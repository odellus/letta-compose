"""HOTL (Human Out of The Loop) mode for Karla.

HOTL mode implements iterative, self-referential agent loops where:
1. The agent receives a prompt
2. Works on the task, modifying files
3. Attempts to complete
4. If not done, receives the SAME prompt again
5. Sees its previous work in files
6. Iterates until completion criteria met

The "self-referential" aspect comes from the agent seeing its own
previous work in files and git history, not from feeding output back as input.
"""

from karla.hotl.state import HOTLState, HOTLStatus, load_state, save_state, clear_state
from karla.hotl.loop import HOTLLoop

__all__ = [
    "HOTLState",
    "HOTLStatus",
    "HOTLLoop",
    "load_state",
    "save_state",
    "clear_state",
]
