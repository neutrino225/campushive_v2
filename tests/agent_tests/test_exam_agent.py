import importlib
import pytest


def test_legacy_exam_agent_removed():
    with pytest.raises(ImportError):
        importlib.import_module("multiagent.agents.exam_agent")
