#!/usr/bin/env python3
"""
Verifies that required Bitbucket environment variables are set.

Usage:
    python3 check-credentials.py

Exits with code 0 if all credentials are present, 1 if any are missing.
If settings.local.json exists but is missing credential keys, adds placeholders
for the missing ones instead of recreating the file from scratch.
"""

import json
import os
import subprocess
import sys

REQUIRED = ["BITBUCKET_USER", "BITBUCKET_TOKEN"]

PLACEHOLDERS = {
    "BITBUCKET_USER": "<your-bitbucket-email>",
    "BITBUCKET_TOKEN": "<your-app-password>",
}

missing = [v for v in REQUIRED if not os.environ.get(v)]

if missing:
    print(f"Missing credentials: {', '.join(missing)}")

    settings_path = os.path.join(os.getcwd(), ".claude", "settings.local.json")

    if os.path.exists(settings_path):
        # File exists — merge missing keys into the env section
        with open(settings_path) as f:
            settings = json.load(f)
        settings.setdefault("env", {})
        added = []
        for key in missing:
            if key not in settings["env"]:
                settings["env"][key] = PLACEHOLDERS[key]
                added.append(key)
        if added:
            with open(settings_path, "w") as f:
                json.dump(settings, f, indent=2)
                f.write("\n")
            print(f"Added missing keys to .claude/settings.local.json: {', '.join(added)}")
        else:
            print("Keys are in settings.local.json but not loaded — did you restart Claude Code?")
    else:
        # File doesn't exist — create it from scratch
        print("Running setup...")
        setup_script = os.path.join(os.path.dirname(__file__), "setup.py")
        subprocess.run([sys.executable, setup_script], check=True)

    print()
    print("Fill in .claude/settings.local.json:")
    print("  BITBUCKET_USER  — your Bitbucket account email")
    print("  BITBUCKET_TOKEN — App Password (Bitbucket Account Settings → App passwords)")
    print()
    print("Then restart Claude Code and re-run /pr-review.")
    sys.exit(1)

print("Credentials OK")
