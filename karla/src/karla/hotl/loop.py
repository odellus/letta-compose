"""HOTL loop execution.

This module provides the HOTLLoop class that integrates with the
hooks system to create self-referential agent loops.
"""

import logging
from typing import Any

from karla.hotl.state import (
    HOTLState,
    HOTLStatus,
    load_state,
    save_state,
    clear_state,
)

logger = logging.getLogger(__name__)


class HOTLLoop:
    """Manages HOTL loop execution via hooks.

    The loop works by:
    1. on_loop_end hook checks for active HOTL state
    2. If active and not complete, injects the same prompt back
    3. The agent sees its previous work in files
    4. Continues until completion promise or max iterations
    """

    def __init__(self, working_dir: str):
        self.working_dir = working_dir

    def start(
        self,
        prompt: str,
        max_iterations: int = 0,
        completion_promise: str | None = None,
        auto_respond: bool = False,
    ) -> HOTLState:
        """Start a new HOTL loop.

        Args:
            prompt: The prompt to repeat each iteration
            max_iterations: Max iterations (0 = unlimited)
            completion_promise: Text that signals completion
            auto_respond: If True, agent predicts user responses instead of waiting

        Returns:
            Initial HOTLState
        """
        state = HOTLState(
            prompt=prompt,
            iteration=1,
            max_iterations=max_iterations,
            completion_promise=completion_promise,
            auto_respond=auto_respond,
        )
        save_state(self.working_dir, state)
        logger.info(
            "HOTL loop started: max_iterations=%d, promise=%s, auto_respond=%s",
            max_iterations,
            completion_promise,
            auto_respond,
        )
        return state

    def cancel(self) -> tuple[bool, int]:
        """Cancel the active HOTL loop.

        Returns:
            Tuple of (was_active, iteration_count)
        """
        state = load_state(self.working_dir)
        if state:
            iteration = state.iteration
            clear_state(self.working_dir)
            logger.info("HOTL loop cancelled at iteration %d", iteration)
            return True, iteration
        return False, 0

    def get_state(self) -> HOTLState | None:
        """Get current HOTL state if active."""
        return load_state(self.working_dir)

    def is_active(self) -> bool:
        """Check if a HOTL loop is active."""
        return load_state(self.working_dir) is not None

    def check_and_continue(self, agent_output: str) -> dict[str, Any] | None:
        """Check if loop should continue and return next action.

        Called from on_loop_end hook.

        Args:
            agent_output: The agent's last output text

        Returns:
            Dict with action info if loop should continue:
            - inject_message: The prompt to send
            - iteration: Current iteration number
            - status_message: Status to display
            - auto_respond: Whether this is an auto-respond iteration

            None if loop should end.
        """
        state = load_state(self.working_dir)
        if not state:
            return None

        # Check for completion promise
        if state.check_completion(agent_output):
            logger.info(
                "HOTL loop completed: promise '%s' detected",
                state.completion_promise,
            )
            clear_state(self.working_dir)
            return None

        # Check max iterations
        if state.max_iterations > 0 and state.iteration >= state.max_iterations:
            logger.info(
                "HOTL loop ended: max iterations (%d) reached",
                state.max_iterations,
            )
            clear_state(self.working_dir)
            return None

        # Continue loop - increment iteration
        state.iteration += 1
        save_state(self.working_dir, state)

        # Build status message
        if state.completion_promise:
            status = (
                f"HOTL iteration {state.iteration}"
                + (f"/{state.max_iterations}" if state.max_iterations > 0 else "")
                + f" | Complete: <promise>{state.completion_promise}</promise>"
            )
        else:
            status = (
                f"HOTL iteration {state.iteration}"
                + (f"/{state.max_iterations}" if state.max_iterations > 0 else "")
            )

        if state.auto_respond:
            status += " | auto-respond"

        logger.info("HOTL loop continuing: iteration %d, auto_respond=%s", state.iteration, state.auto_respond)

        # Determine inject message based on auto_respond mode
        if state.auto_respond:
            # In auto-respond mode, ask agent to predict what user would say
            inject_message = (
                "Based on my previous responses and our current task priorities, "
                "predict what I (the user) would respond to continue this task. "
                "Generate my response, then continue working on the task.\n\n"
                f"Original task: {state.prompt}"
            )
        else:
            # Standard HOTL - re-inject same prompt
            inject_message = state.prompt

        return {
            "inject_message": inject_message,
            "iteration": state.iteration,
            "status_message": status,
            "auto_respond": state.auto_respond,
        }


def create_hotl_hooks(working_dir: str) -> dict[str, list]:
    """Create hook callbacks for HOTL mode.

    Returns a dict of hook event -> callbacks that can be
    added to a HooksManager.

    Args:
        working_dir: Working directory for state file

    Returns:
        Dict mapping event names to callback lists
    """
    loop = HOTLLoop(working_dir)

    async def on_loop_end_hook(data: dict[str, Any]) -> dict[str, Any] | None:
        """Hook called when agent loop ends."""
        agent_output = data.get("text", "")

        result = loop.check_and_continue(agent_output)
        if result:
            # Return inject_message to continue the loop
            return {
                "inject_message": (
                    f"<system-reminder>\n"
                    f"{result['status_message']}\n"
                    f"</system-reminder>\n\n"
                    f"{result['inject_message']}"
                ),
            }
        return None

    async def on_message_hook(data: dict[str, Any]) -> dict[str, Any] | None:
        """Hook to add HOTL status to messages."""
        state = loop.get_state()
        if state:
            # Could add iteration info to output
            pass
        return None

    return {
        "on_loop_end": [on_loop_end_hook],
        "on_message": [on_message_hook],
    }
