#!/usr/bin/env bash
#
# config-upgrade.sh - Upgrade config.yaml to match config.example.yaml
#
# 1. Runs version-specific migrations (value replacements, renames, etc.)
# 2. Merges missing fields from the example into the user config
# 3. Backs up config.yaml to config.yaml.bak before modifying.

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE="$REPO_ROOT/config.example.yaml"

# Resolve config.yaml location: env var > backend/ > repo root
if [ -n "$DEER_FLOW_CONFIG_PATH" ] && [ -f "$DEER_FLOW_CONFIG_PATH" ]; then
    CONFIG="$DEER_FLOW_CONFIG_PATH"
elif [ -f "$REPO_ROOT/backend/config.yaml" ]; then
    CONFIG="$REPO_ROOT/backend/config.yaml"
elif [ -f "$REPO_ROOT/config.yaml" ]; then
    CONFIG="$REPO_ROOT/config.yaml"
else
    CONFIG=""
fi

if [ ! -f "$EXAMPLE" ]; then
    echo "✗ config.example.yaml not found at $EXAMPLE"
    exit 1
fi

if [ -z "$CONFIG" ]; then
    echo "No config.yaml found — creating from example..."
    cp "$EXAMPLE" "$REPO_ROOT/config.yaml"
    echo "OK config.yaml created. Please review and set your API keys."
    exit 0
fi

# Use inline Python to do migrations + recursive merge with PyYAML
if command -v cygpath >/dev/null 2>&1; then
    CONFIG_WIN="$(cygpath -w "$CONFIG")"
    EXAMPLE_WIN="$(cygpath -w "$EXAMPLE")"
else
    CONFIG_WIN="$CONFIG"
    EXAMPLE_WIN="$EXAMPLE"
fi

cd "$REPO_ROOT/backend" && CONFIG_WIN_PATH="$CONFIG_WIN" EXAMPLE_WIN_PATH="$EXAMPLE_WIN" uv run python -c "
import os
import sys, shutil, copy, re
from pathlib import Path

import yaml

config_path = Path(os.environ['CONFIG_WIN_PATH'])
example_path = Path(os.environ['EXAMPLE_WIN_PATH'])

with open(config_path, encoding='utf-8') as f:
    raw_text = f.read()
    user = yaml.safe_load(raw_text) or {}

with open(example_path, encoding='utf-8') as f:
    example = yaml.safe_load(f) or {}

def parse_config_version(value, label):
    if value is None:
        return 0
    if isinstance(value, bool):
        value = str(value)
    if isinstance(value, int):
        version = value
    elif isinstance(value, str):
        try:
            version = int(value.strip())
        except ValueError:
            version = -1
    else:
        version = -1
    if version < 0:
        print(f'ERROR: {label} config_version must be a non-negative integer; got {value!r}.', file=sys.stderr)
        sys.exit(2)
    return version

user_version = parse_config_version(user.get('config_version', 0), 'config.yaml')
example_version = parse_config_version(example.get('config_version', 0), 'config.example.yaml')

if user_version >= example_version:
    print(f'OK config.yaml is already up to date (version {user_version}).')
    sys.exit(0)

print(f'Upgrading config.yaml: version {user_version} -> {example_version}')
print()

# ── Migrations ───────────────────────────────────────────────────────────
# Each migration targets a specific version upgrade.
# 'replacements': list of (old_string, new_string) applied to the raw YAML text.
#   This handles value changes that a dict merge cannot catch.

MIGRATIONS = {
    1: {
        'description': 'Rename src.* module paths to deerflow.*',
        'replacements': [
            ('src.community.', 'deerflow.community.'),
            ('src.sandbox.', 'deerflow.sandbox.'),
            ('src.models.', 'deerflow.models.'),
            ('src.tools.', 'deerflow.tools.'),
        ],
    },
    6: {
        'description': 'Remove legacy sandbox providers and tools',
        'replacements': [],
    },
    # Future migrations go here:
    # 2: {
    #     'description': '...',
    #     'replacements': [('old', 'new')],
    # },
}

# Apply migrations in order for versions (user_version, example_version]
migrated = []
for version in range(user_version + 1, example_version + 1):
    migration = MIGRATIONS.get(version)
    if not migration:
        continue
    desc = migration.get('description', f'Migration to v{version}')
    for old, new in migration.get('replacements', []):
        if old in raw_text:
            raw_text = raw_text.replace(old, new)
            migrated.append(f'{old} -> {new}')

# Re-parse after text migrations
user = yaml.safe_load(raw_text) or {}

if user_version < 6 <= example_version:
    obsolete_tool_prefix = 'deerflow.sandbox.tools:'
    configured_tools = user.get('tools')
    if isinstance(configured_tools, list):
        retained_tools = []
        for tool in configured_tools:
            use = tool.get('use') if isinstance(tool, dict) else None
            if isinstance(use, str) and use.startswith(obsolete_tool_prefix):
                migrated.append(f'removed obsolete tool {use}')
                continue
            retained_tools.append(tool)
        user['tools'] = retained_tools

        retained_group_names = {
            tool.get('group')
            for tool in retained_tools
            if isinstance(tool, dict) and isinstance(tool.get('group'), str)
        }
        obsolete_group_names = {'file:read', 'file:write', 'bash'}
        configured_groups = user.get('tool_groups')
        if isinstance(configured_groups, list):
            retained_groups = []
            for group in configured_groups:
                name = group.get('name') if isinstance(group, dict) else None
                if name in obsolete_group_names and name not in retained_group_names:
                    migrated.append(f'removed orphaned tool group {name}')
                    continue
                retained_groups.append(group)
            user['tool_groups'] = retained_groups

    obsolete_sandbox_providers = {
        'deerflow.sandbox.local:LocalSandboxProvider',
        'deerflow.community.aio_sandbox:AioSandboxProvider',
    }
    sandbox = user.get('sandbox')
    if isinstance(sandbox, dict) and sandbox.get('use') in obsolete_sandbox_providers:
        provider = sandbox.get('use')
        migrated.append(f'disabled obsolete sandbox provider {provider}')
        user['sandbox'] = None

if migrated:
    print(f'Applied {len(migrated)} migration(s):')
    for m in migrated:
        print(f'  ~ {m}')
    print()

# ── Merge missing fields ─────────────────────────────────────────────────

added = []

def merge(target, source, path=''):
    \"\"\"Recursively merge source into target, adding missing keys only.\"\"\"
    for key, value in source.items():
        key_path = f'{path}.{key}' if path else key
        if key not in target:
            target[key] = copy.deepcopy(value)
            added.append(key_path)
        elif isinstance(value, dict) and isinstance(target[key], dict):
            merge(target[key], value, key_path)

merge(user, example)

# Always update config_version
user['config_version'] = example_version

# ── Write ─────────────────────────────────────────────────────────────────

backup = config_path.with_suffix('.yaml.bak')
shutil.copy2(config_path, backup)
print(f'Backed up to {backup.name}')

with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(user, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

if added:
    print(f'Added {len(added)} new field(s):')
    for a in added:
        print(f'  + {a}')

if not migrated and not added:
    print('No changes needed (version bumped only).')

print()
print(f'OK config.yaml upgraded to version {example_version}.')
print('  Please review the changes and set any new required values.')
"
