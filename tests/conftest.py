"""Test configuration for Octopus French Energy."""

import os
import sys

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


@pytest.fixture(autouse=True)
def enable_custom_integrations():
    """Enable custom integrations defined in the test dir."""
    yield
