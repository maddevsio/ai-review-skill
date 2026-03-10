#!/usr/bin/env python3
"""
Creates .claude/settings.local.json with GitLab credential placeholders.

Usage:
    python3 setup.py

Run once per project. Fill in the generated file before using the skill.
"""

import json
import os
import sys


def main() -> None:
    settings_path = os.path.join(os.getcwd(), ".claude", "settings.local.json")

    if os.path.exists(settings_path):
        print("settings.local.json already exists, skipping.")
        sys.exit(0)

    template = {
        "env": {
            "GITLAB_TOKEN": "<your-personal-access-token>",
        }
    }

    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(template, f, indent=2)
        f.write("\n")

    print("Created .claude/settings.local.json")
    print()
    print("Fill in the values before using the skill:")
    print()
    print("  GITLAB_TOKEN — Personal Access Token")
    print("                 Create at: GitLab → User Settings → Access Tokens")
    print("                 Required scope: api")


if __name__ == "__main__":
    main()
