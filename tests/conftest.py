import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_records():
    with open(FIXTURES / "sample_enforcement.json", encoding="utf-8") as fh:
        return json.load(fh)
