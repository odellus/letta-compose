"""Setup script for karla evals.

Creates the test environment before running evaluations.
"""

import os
from pathlib import Path

from letta_evals.decorators import suite_setup


@suite_setup
def prepare_eval_environment() -> None:
    """Prepare the evaluation environment.

    Creates test files and directories needed by the eval samples.
    """
    eval_dir = Path("/tmp/karla-eval")
    eval_dir.mkdir(parents=True, exist_ok=True)

    # Create test file for read tests
    test_file = eval_dir / "test.txt"
    test_file.write_text("hello world")

    # Clean up any previous output files
    output_file = eval_dir / "output.txt"
    if output_file.exists():
        output_file.unlink()

    print(f"Eval environment prepared at {eval_dir}")
