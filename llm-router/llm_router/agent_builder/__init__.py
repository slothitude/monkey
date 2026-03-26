"""Agent Builder module for creating pi agents."""

from llm_router.agent_builder.skills import (
    generate_skill,
    get_available_templates as get_skill_templates,
    get_template as get_skill_template,
    SKILL_TEMPLATES,
    SkillCategory,
    SkillTemplate,
)
from llm_router.agent_builder.extensions import (
    generate_extension,
    get_available_templates as get_extension_templates,
    get_template as get_extension_template,
    EXTENSION_TEMPLATES,
    ExtensionType,
    ExtensionTemplate,
)
from llm_router.agent_builder.prompts import (
    generate_prompt,
    get_available_templates as get_prompt_templates,
    get_template as get_prompt_template,
    PROMPT_TEMPLATES,
    PromptStyle,
    PromptTemplate,
)

__all__ = [
    # Skills
    "generate_skill",
    "get_skill_templates",
    "get_skill_template",
    "SKILL_TEMPLATES",
    "SkillCategory",
    "SkillTemplate",
    # Extensions
    "generate_extension",
    "get_extension_templates",
    "get_extension_template",
    "EXTENSION_TEMPLATES",
    "ExtensionType",
    "ExtensionTemplate",
    # Prompts
    "generate_prompt",
    "get_prompt_templates",
    "get_prompt_template",
    "PROMPT_TEMPLATES",
    "PromptStyle",
    "PromptTemplate",
]
