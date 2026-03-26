"""Skill generator for pi agents."""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class SkillCategory(str, Enum):
    """Categories of skills."""
    CODE = "code"
    RESEARCH = "research"
    WRITING = "writing"
    DATA = "data"
    AUTOMATION = "automation"
    COMMUNICATION = "communication"
    ANALYSIS = "analysis"


@dataclass
class SkillTemplate:
    """Template for a pi skill."""
    name: str
    description: str
    category: SkillCategory
    content: str
    triggers: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


# Skill templates
SKILL_TEMPLATES: dict[str, str] = {
    "code-reviewer": """# Code Reviewer Skill

## Purpose
Reviews code for bugs, security vulnerabilities, and best practices.

## Triggers
- "review this code"
- "check for bugs"
- "security review"
- "code review"

## Behavior
When activated:
1. Analyze the provided code for:
   - Security vulnerabilities (OWASP Top 10)
   - Logic errors and bugs
   - Performance issues
   - Code style and best practices
   - Documentation completeness

2. Provide structured feedback:
   - Critical issues (must fix)
   - Warnings (should fix)
   - Suggestions (nice to have)

3. Include specific line numbers and code examples for fixes.

## Example
User: "Review this function"
```
def get_user(id):
    return db.query(f"SELECT * FROM users WHERE id = {id}")
```

Response:
- CRITICAL: SQL injection vulnerability. Use parameterized queries.
- SUGGESTION: Add input validation and error handling.
""",

    "research-agent": """# Research Agent Skill

## Purpose
Conducts thorough research on topics using web search and analysis.

## Triggers
- "research"
- "find information about"
- "look up"
- "investigate"

## Behavior
1. Break down complex questions into searchable components
2. Use multiple search queries for comprehensive coverage
3. Verify information across multiple sources
4. Cite sources with URLs
5. Summarize findings with key insights
6. Note any conflicting information or uncertainty

## Output Format
- Summary (2-3 sentences)
- Key Findings (bullet points)
- Sources (with URLs)
- Confidence Level (high/medium/low)
""",

    "test-generator": """# Test Generator Skill

## Purpose
Generates comprehensive test suites for code.

## Triggers
- "generate tests"
- "write unit tests"
- "test this code"
- "add test coverage"

## Behavior
1. Analyze code structure and identify testable units
2. Generate tests covering:
   - Happy path scenarios
   - Edge cases
   - Error conditions
   - Boundary values
3. Use appropriate testing framework (pytest, jest, etc.)
4. Include descriptive test names
5. Add comments explaining test purpose

## Example Output
```python
def test_calculate_discount_with_valid_percentage():
    '''Test that discount is correctly calculated for valid input.'''
    result = calculate_discount(100, 20)
    assert result == 80

def test_calculate_discount_with_zero_percentage():
    '''Test that zero discount returns original price.'''
    result = calculate_discount(100, 0)
    assert result == 100

def test_calculate_discount_with_invalid_percentage():
    '''Test that invalid percentage raises ValueError.'''
    with pytest.raises(ValueError):
        calculate_discount(100, 150)
```
""",

    "documentation-writer": """# Documentation Writer Skill

## Purpose
Creates clear, comprehensive documentation for code and APIs.

## Triggers
- "document this"
- "write docs"
- "generate documentation"
- "add docstrings"

## Behavior
1. Analyze code structure, parameters, and return values
2. Generate documentation in appropriate format:
   - Docstrings for functions/classes
   - README sections for projects
   - API documentation for endpoints
3. Include:
   - Purpose/description
   - Parameters with types
   - Return values
   - Usage examples
   - Error conditions

## Example
```python
def process_data(data: list[dict], filter_key: str) -> list[dict]:
    '''Process and filter a list of dictionaries.

    Args:
        data: List of dictionaries to process.
        filter_key: Key to filter dictionaries by. Only dictionaries
                   containing this key will be included.

    Returns:
        Filtered list of dictionaries with processed values.

    Raises:
        ValueError: If data is empty or filter_key is empty.

    Example:
        >>> process_data([{'a': 1}, {'b': 2}], 'a')
        [{'a': 1}]
    '''
```
""",
}


def generate_skill(
    name: str,
    description: str,
    category: SkillCategory = SkillCategory.AUTOMATION,
    custom_instructions: Optional[str] = None,
    include_examples: bool = True,
) -> SkillTemplate:
    """
    Generate a pi skill based on the description.

    Args:
        name: Name of the skill (kebab-case)
        description: Description of what the skill should do
        category: Category of the skill
        custom_instructions: Additional instructions for skill behavior
        include_examples: Whether to include usage examples

    Returns:
        SkillTemplate with generated content
    """
    # Generate skill content based on description
    content = f"""# {name.replace('-', ' ').title()} Skill

## Purpose
{description}

## Triggers
- "{name}"
- "{name.replace('-', ' ')}"
- "use {name}"

## Behavior
{custom_instructions or 'When activated, perform the described task with attention to detail and accuracy.'}

## Guidelines
1. Always confirm understanding of the task
2. Break complex tasks into steps
3. Provide clear, actionable output
4. Handle errors gracefully
"""

    if include_examples:
        content += """
## Example Usage
User: "Use {name} to help me with my task"
Response: [Execute the skill based on the description above]
"""

    return SkillTemplate(
        name=name,
        description=description,
        category=category,
        content=content,
        triggers=[name, name.replace("-", " ")],
        examples=[f"Use {name} to help with this task"] if include_examples else [],
    )


def get_available_templates() -> list[dict]:
    """Get list of available skill templates."""
    return [
        {"id": key, "name": key.replace("-", " ").title(), "preview": value[:200] + "..."}
        for key, value in SKILL_TEMPLATES.items()
    ]


def get_template(name: str) -> Optional[str]:
    """Get a specific template by name."""
    return SKILL_TEMPLATES.get(name)
