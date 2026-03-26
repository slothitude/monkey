"""Extension generator for pi agents."""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ExtensionType(str, Enum):
    """Types of extensions."""
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"
    HOOK = "hook"


@dataclass
class ExtensionTemplate:
    """Template for a pi extension."""
    name: str
    description: str
    extension_type: ExtensionType
    code: str
    dependencies: list[str] = field(default_factory=list)
    config_schema: Optional[dict] = None


# Extension templates
EXTENSION_TEMPLATES: dict[str, str] = {
    "web-scraper": """import { z } from 'zod';
import { tool } from '@anthropic-ai/sdk';

/**
 * Web Scraper Extension
 * Scrapes content from web pages
 */
export const webScraperTool = tool({
  name: 'web_scraper',
  description: 'Scrape content from a web page URL',
  parameters: z.object({
    url: z.string().url().describe('The URL to scrape'),
    selector: z.string().optional().describe('CSS selector to extract specific content'),
  }),
  execute: async ({ url, selector }) => {
    const response = await fetch(url);
    const html = await response.text();

    // Basic content extraction
    // In production, use a proper HTML parser
    const content = html;

    return {
      success: true,
      content: selector ? `Extracted from ${selector}: ${content}` : content,
      url,
    };
  },
});

export default webScraperTool;
""",

    "database-query": """import { z } from 'zod';
import { tool } from '@anthropic-ai/sdk';

/**
 * Database Query Extension
 * Execute safe parameterized queries
 */
export const databaseQueryTool = tool({
  name: 'database_query',
  description: 'Execute a safe parameterized database query',
  parameters: z.object({
    query: z.string().describe('SQL query with $1, $2, etc. placeholders'),
    params: z.array(z.any()).describe('Parameters for the query'),
    read_only: z.boolean().default(true).describe('Whether this is a read-only query'),
  }),
  execute: async ({ query, params, read_only }) => {
    // Implementation would connect to your database
    // This is a placeholder
    return {
      success: true,
      rows: [],
      rowCount: 0,
      query: read_only ? query : 'BLOCKED: Write queries not allowed',
    };
  },
});

export default databaseQueryTool;
""",

    "file-manager": """import { z } from 'zod';
import { tool } from '@anthropic-ai/sdk';
import * as fs from 'fs/promises';
import * as path from 'path';

/**
 * File Manager Extension
 * Safe file operations within a sandboxed directory
 */
const SANDBOX_DIR = process.env.SANDBOX_DIR || './sandbox';

function sanitizePath(filePath: string): string {
  const resolved = path.resolve(SANDBOX_DIR, filePath);
  if (!resolved.startsWith(SANDBOX_DIR)) {
    throw new Error('Path traversal not allowed');
  }
  return resolved;
}

export const fileManagerTool = tool({
  name: 'file_manager',
  description: 'Manage files within a sandboxed directory',
  parameters: z.object({
    action: z.enum(['read', 'write', 'list', 'delete']).describe('Action to perform'),
    path: z.string().describe('Relative path within sandbox'),
    content: z.string().optional().describe('Content to write (for write action)'),
  }),
  execute: async ({ action, path: filePath, content }) => {
    const safePath = sanitizePath(filePath);

    switch (action) {
      case 'read': {
        const data = await fs.readFile(safePath, 'utf-8');
        return { success: true, content: data };
      }
      case 'write': {
        if (!content) throw new Error('Content required for write action');
        await fs.writeFile(safePath, content, 'utf-8');
        return { success: true, message: 'File written' };
      }
      case 'list': {
        const entries = await fs.readdir(safePath, { withFileTypes: true });
        return {
          success: true,
          entries: entries.map(e => ({
            name: e.name,
            type: e.isDirectory() ? 'directory' : 'file',
          })),
        };
      }
      case 'delete': {
        await fs.unlink(safePath);
        return { success: true, message: 'File deleted' };
      }
    }
  },
});

export default fileManagerTool;
""",

    "api-client": """import { z } from 'zod';
import { tool } from '@anthropic-ai/sdk';

/**
 * API Client Extension
 * Make HTTP requests to external APIs
 */
export const apiClientTool = tool({
  name: 'api_client',
  description: 'Make HTTP requests to external APIs',
  parameters: z.object({
    method: z.enum(['GET', 'POST', 'PUT', 'DELETE']).default('GET'),
    url: z.string().url().describe('The API endpoint URL'),
    headers: z.record(z.string()).optional().describe('Request headers'),
    body: z.any().optional().describe('Request body (for POST/PUT)'),
    timeout: z.number().default(30000).describe('Timeout in milliseconds'),
  }),
  execute: async ({ method, url, headers, body, timeout }) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...headers,
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      const data = await response.json();

      return {
        success: response.ok,
        status: response.status,
        data,
      };
    } finally {
      clearTimeout(timeoutId);
    }
  },
});

export default apiClientTool;
""",
}


def generate_extension(
    name: str,
    description: str,
    extension_type: ExtensionType = ExtensionType.TOOL,
    custom_code: Optional[str] = None,
    dependencies: Optional[list[str]] = None,
) -> ExtensionTemplate:
    """
    Generate a pi extension based on the description.

    Args:
        name: Name of the extension (kebab-case)
        description: Description of what the extension does
        extension_type: Type of extension
        custom_code: Custom code to include
        dependencies: List of npm dependencies

    Returns:
        ExtensionTemplate with generated code
    """
    camel_name = ''.join(word.capitalize() for word in name.split('-'))

    code = custom_code or f"""import {{ z }} from 'zod';
import {{ tool }} from '@anthropic-ai/sdk';

/**
 * {camel_name} Extension
 * {description}
 */
export const {camel_name[0].lower() + camel_name[1:]}Tool = tool({{
  name: '{name}',
  description: '{description}',
  parameters: z.object({{
    // Define your parameters here
    input: z.string().describe('Input parameter description'),
  }}),
  execute: async ({{ input }}) => {{
    // Implementation here
    return {{
      success: true,
      result: input,
    }};
  }},
}});

export default {camel_name[0].lower() + camel_name[1:]}Tool;
"""

    return ExtensionTemplate(
        name=name,
        description=description,
        extension_type=extension_type,
        code=code,
        dependencies=dependencies or ['zod', '@anthropic-ai/sdk'],
    )


def get_available_templates() -> list[dict]:
    """Get list of available extension templates."""
    return [
        {"id": key, "name": key.replace("-", " ").title(), "preview": value[:200] + "..."}
        for key, value in EXTENSION_TEMPLATES.items()
    ]


def get_template(name: str) -> Optional[str]:
    """Get a specific template by name."""
    return EXTENSION_TEMPLATES.get(name)
