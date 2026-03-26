#!/usr/bin/env python
"""Run tests for LLM Router."""

import subprocess
import sys


def main():
    """Run pytest with coverage."""
    args = [
        "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "--cov=llm_router",
        "--cov-report=term-missing",
        "--cov-report=html",
    ]

    result = subprocess.run(args)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
