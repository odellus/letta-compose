"""HOTL state management.

State is persisted to .karla/hotl-loop.md in the working directory.
"""

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

# State file location
STATE_FILE = ".karla/hotl-loop.md"


class HOTLStatus(Enum):
    """Status of a HOTL loop."""
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MAX_ITERATIONS = "max_iterations"


@dataclass
class HOTLState:
    """State of an active HOTL loop."""
    prompt: str
    iteration: int = 1
    max_iterations: int = 0  # 0 = unlimited
    completion_promise: str | None = None
    status: HOTLStatus = HOTLStatus.RUNNING
    auto_respond: bool = False  # If True, agent predicts user responses instead of waiting

    def should_continue(self) -> bool:
        """Check if the loop should continue."""
        if self.status != HOTLStatus.RUNNING:
            return False
        if self.max_iterations > 0 and self.iteration >= self.max_iterations:
            return False
        return True

    def check_completion(self, output: str) -> bool:
        """Check if output contains completion promise.

        Looks for <promise>TEXT</promise> tags and checks if TEXT
        matches the completion_promise.
        """
        if not self.completion_promise:
            return False

        # Extract text from <promise> tags
        match = re.search(r'<promise>(.*?)</promise>', output, re.DOTALL)
        if match:
            promise_text = match.group(1).strip()
            # Normalize whitespace
            promise_text = ' '.join(promise_text.split())
            return promise_text == self.completion_promise

        return False


def get_state_path(working_dir: str) -> Path:
    """Get the path to the state file."""
    return Path(working_dir) / STATE_FILE


def load_state(working_dir: str) -> HOTLState | None:
    """Load HOTL state from file.

    Args:
        working_dir: Working directory

    Returns:
        HOTLState if active loop exists, None otherwise
    """
    state_path = get_state_path(working_dir)
    if not state_path.exists():
        return None

    try:
        content = state_path.read_text()
        return _parse_state_file(content)
    except Exception:
        return None


def save_state(working_dir: str, state: HOTLState) -> None:
    """Save HOTL state to file.

    Args:
        working_dir: Working directory
        state: State to save
    """
    state_path = get_state_path(working_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    content = _format_state_file(state)
    state_path.write_text(content)


def clear_state(working_dir: str) -> bool:
    """Clear HOTL state (cancel loop).

    Args:
        working_dir: Working directory

    Returns:
        True if state was cleared, False if no state existed
    """
    state_path = get_state_path(working_dir)
    if state_path.exists():
        state_path.unlink()
        return True
    return False


def _parse_state_file(content: str) -> HOTLState | None:
    """Parse state file content.

    Format:
    ---
    iteration: 1
    max_iterations: 50
    completion_promise: "DONE"
    ---

    The actual prompt text here...
    """
    # Split frontmatter and content
    parts = content.split('---', 2)
    if len(parts) < 3:
        return None

    frontmatter = parts[1].strip()
    prompt = parts[2].strip()

    # Parse frontmatter
    iteration = 1
    max_iterations = 0
    completion_promise = None
    auto_respond = False

    for line in frontmatter.split('\n'):
        line = line.strip()
        if line.startswith('iteration:'):
            try:
                iteration = int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith('max_iterations:'):
            try:
                max_iterations = int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith('completion_promise:'):
            value = line.split(':', 1)[1].strip()
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            if value and value != 'null':
                completion_promise = value
        elif line.startswith('auto_respond:'):
            value = line.split(':', 1)[1].strip().lower()
            auto_respond = value == 'true'

    return HOTLState(
        prompt=prompt,
        iteration=iteration,
        max_iterations=max_iterations,
        completion_promise=completion_promise,
        auto_respond=auto_respond,
    )


def _format_state_file(state: HOTLState) -> str:
    """Format state for file storage."""
    promise_str = f'"{state.completion_promise}"' if state.completion_promise else 'null'
    auto_respond_str = 'true' if state.auto_respond else 'false'

    return f"""---
iteration: {state.iteration}
max_iterations: {state.max_iterations}
completion_promise: {promise_str}
auto_respond: {auto_respond_str}
---

{state.prompt}
"""
