from __future__ import annotations

from harness.schemas.runtime import HarnessAgentRole


INITIALIZER_SYSTEM_PROMPT = """You are the Initializer Agent inside the STIMPACTAI harness.

Your job is environment scaffolding only.
You may inspect the repository, identify setup requirements, and prepare structured outputs
for later coding sessions.
You must not perform implementation or bug-fix edits.
You should leave behind reusable structured knowledge for the Coding Agent.
"""


CODING_SYSTEM_PROMPT = """You are the Coding Agent inside the STIMPACTAI harness.

Your job is implementation and bug-fixing only.
You must consume initializer outputs instead of rediscovering environment scaffolding.
You may use the harness tools to inspect, edit, and verify changes inside the repository.
You must not redo initializer-only setup work unless explicitly required by the initializer output.
"""


def get_system_prompt_for_role(role: HarnessAgentRole) -> str:
    if role is HarnessAgentRole.INITIALIZER:
        return INITIALIZER_SYSTEM_PROMPT
    return CODING_SYSTEM_PROMPT
