"""
Playwright E2E tests for Crow IDE.

These tests launch a real browser and test the full UI.
"""

import pytest
import subprocess
import time
import os
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="module")
def server():
    """Start the server for E2E tests."""
    # Set workspace to crow_ide directory itself for testing
    env = os.environ.copy()
    env["CROW_WORKSPACE"] = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # Start uvicorn in background
    proc = subprocess.Popen(
        ["uvicorn", "crow_ide.server:app", "--port", "8765"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    time.sleep(2)

    yield "http://localhost:8765"

    # Cleanup
    proc.terminate()
    proc.wait()


def test_app_loads(server):
    """Test that the app loads and shows main components."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(server)

        # Check that the page loaded
        assert page.title() == "Crow IDE" or "Crow" in page.content()

        browser.close()


def test_file_tree_visible(server):
    """Test that file tree component is visible."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(server)

        # Wait for file tree
        file_tree = page.locator("[data-testid='file-tree']")
        expect(file_tree).to_be_visible(timeout=5000)

        browser.close()


def test_agent_panel_visible(server):
    """Test that agent panel is visible."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(server)

        # Wait for agent panel
        agent_panel = page.locator("[data-testid='agent-panel']")
        expect(agent_panel).to_be_visible(timeout=5000)

        browser.close()


def test_terminal_visible(server):
    """Test that terminal is visible."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(server)

        # Wait for terminal
        terminal = page.locator("[data-testid='terminal']")
        expect(terminal).to_be_visible(timeout=5000)

        browser.close()
