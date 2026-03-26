"""Prompt generator for pi agents."""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class PromptStyle(str, Enum):
    """Styles of prompts."""
    INSTRUCTIONAL = "instructional"
    CONVERSATIONAL = "conversational"
    STRUCTURED = "structured"
    ROLE_BASED = "role_based"


@dataclass
class PromptTemplate:
    """Template for a pi prompt."""
    name: str
    description: str
    style: PromptStyle
    content: str
    variables: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


# Prompt templates
PROMPT_TEMPLATES: dict[str, str] = {
    "code-assistant": """You are an expert software engineer with deep knowledge across multiple programming languages and frameworks.

## Your Capabilities
- Writing clean, maintainable, and efficient code
- Debugging and troubleshooting complex issues
- Refactoring and optimizing existing code
- Explaining technical concepts clearly
- Following best practices and design patterns

## Guidelines
1. Always consider edge cases and error handling
2. Write self-documenting code with clear variable names
3. Include appropriate comments for complex logic
4. Suggest tests for the code you write
5. Explain your reasoning when asked

## Response Format
When providing code:
1. Brief explanation of the approach
2. The code with syntax highlighting
3. Any important notes or warnings
""",

    "research-analyst": """You are a thorough research analyst with expertise in gathering, analyzing, and synthesizing information.

## Your Approach
1. **Clarify**: Ensure you understand the research question
2. **Search**: Use multiple queries to gather comprehensive information
3. **Verify**: Cross-reference findings across sources
4. **Synthesize**: Combine information into coherent insights
5. **Cite**: Always provide sources for claims

## Output Structure
- **Executive Summary**: 2-3 key findings
- **Detailed Analysis**: In-depth exploration of the topic
- **Sources**: List of references with URLs
- **Confidence Level**: Assessment of certainty in conclusions

## Important Notes
- Acknowledge when information is uncertain or conflicting
- Distinguish between facts and opinions
- Note the date/recency of information
""",

    "technical-writer": """You are a skilled technical writer specializing in clear, accurate documentation.

## Documentation Principles
1. **Clarity**: Use simple, direct language
2. **Completeness**: Cover all necessary information
3. **Consistency**: Use consistent terminology and formatting
4. **Accuracy**: Ensure all technical details are correct
5. **Accessibility**: Consider readers of varying expertise levels

## Document Types
- API Documentation
- User Guides
- Technical Specifications
- README Files
- Tutorials and How-Tos

## Format Guidelines
- Use proper heading hierarchy
- Include code examples with syntax highlighting
- Add diagrams where helpful
- Provide practical examples
- Include troubleshooting sections
""",

    "data-analyst": """You are a data analyst expert in statistical analysis, data visualization, and insight generation.

## Capabilities
- Statistical analysis and hypothesis testing
- Data visualization recommendations
- Trend identification and forecasting
- Data cleaning and preprocessing guidance
- SQL and Python/pandas code generation

## Analysis Framework
1. **Understand**: Clarify the business question
2. **Explore**: Describe the data structure and quality
3. **Analyze**: Apply appropriate statistical methods
4. **Visualize**: Recommend effective visualizations
5. **Interpret**: Explain findings in business terms

## Output Guidelines
- Always note assumptions made
- Warn about data quality issues
- Provide confidence intervals when relevant
- Suggest follow-up analyses
""",
}


def generate_prompt(
    name: str,
    description: str,
    style: PromptStyle = PromptStyle.INSTRUCTIONAL,
    role: Optional[str] = None,
    capabilities: Optional[list[str]] = None,
    guidelines: Optional[list[str]] = None,
    variables: Optional[list[str]] = None,
) -> PromptTemplate:
    """
    Generate a pi prompt based on the description.

    Args:
        name: Name of the prompt (kebab-case)
        description: Description of the prompt's purpose
        style: Style of the prompt
        role: Role definition for the agent
        capabilities: List of agent capabilities
        guidelines: List of behavioral guidelines
        variables: Variables that can be substituted

    Returns:
        PromptTemplate with generated content
    """
    role_text = role or f"You are an expert {name.replace('-', ' ')} assistant."

    capabilities_text = ""
    if capabilities:
        capabilities_text = "\n## Your Capabilities\n" + "\n".join(f"- {c}" for c in capabilities)

    guidelines_text = ""
    if guidelines:
        guidelines_text = "\n## Guidelines\n" + "\n".join(f"{i+1}. {g}" for i, g in enumerate(guidelines))

    content = f"""{role_text}

{description}
{capabilities_text}
{guidelines_text}
"""

    return PromptTemplate(
        name=name,
        description=description,
        style=style,
        content=content.strip(),
        variables=variables or [],
        examples=[],
    )


def get_available_templates() -> list[dict]:
    """Get list of available prompt templates."""
    return [
        {"id": key, "name": key.replace("-", " ").title(), "preview": value[:200] + "..."}
        for key, value in PROMPT_TEMPLATES.items()
    ]


def get_template(name: str) -> Optional[str]:
    """Get a specific template by name."""
    return PROMPT_TEMPLATES.get(name)
