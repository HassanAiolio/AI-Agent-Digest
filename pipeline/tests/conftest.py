import sys
from pathlib import Path

import pytest
import yaml

PIPELINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg():
    return yaml.safe_load((PIPELINE / "config.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def fixture_text():
    def read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")
    return read


@pytest.fixture(autouse=True)
def no_network_llm(monkeypatch):
    """Tests never call Groq, even with a key in the developer's env."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
