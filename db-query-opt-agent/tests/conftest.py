"""
conftest.py — shared pytest fixtures for the test suite.
Loads api.env from the project root before any test runs.
"""

from pathlib import Path
from dotenv import load_dotenv


def pytest_configure(config):
    """
    Load environment variables once at the start of the test session.
    Walks up from the tests/ directory to find api.env at the project root.
    This keeps tests portable — no hardcoded paths required.
    """
    current = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = current / "api.env"
        if candidate.is_file():
            load_dotenv(candidate)
            return
        current = current.parent
