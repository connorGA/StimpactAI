from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_PLATFORM_ROOT = REPO_ROOT / "agent-platform"

for candidate in (REPO_ROOT, AGENT_PLATFORM_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)
