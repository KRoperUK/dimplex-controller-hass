#!/usr/bin/env bash
# Verify that every non-English translation file in
# custom_components/dimplex/translations/ has the same key shape as en.json.
#
# Fails (exit 1) when any language is missing keys present in en.json, or has
# extra keys not present in en.json. The reference language is en.json — it
# must exist and be valid JSON.
#
# Usage: scripts/check-translation-parity.sh
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
translations_dir="$repo_root/custom_components/dimplex/translations"
reference="en.json"

if [[ ! -f "$translations_dir/$reference" ]]; then
  echo "Reference translation $reference not found in $translations_dir" >&2
  exit 1
fi

# Collect flattened keys with python — portable, no jq requirement.
collect_keys() {
  python3 - "$1" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)

def walk(node, prefix=""):
    out = []
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.extend(walk(value, path))
        else:
            out.append(path)
    return out

for k in walk(data):
    print(k)
PY
}

mapfile -t reference_keys < <(collect_keys "$translations_dir/$reference")
declare -A reference_set
for k in "${reference_keys[@]}"; do
  reference_set["$k"]=1
done

status=0
for lang_file in "$translations_dir"/*.json; do
  name=$(basename "$lang_file")
  [[ "$name" == "$reference" ]] && continue

  if ! mapfile -t lang_keys < <(collect_keys "$lang_file"); then
    echo "✗ $name: invalid JSON" >&2
    status=1
    continue
  fi

  declare -A lang_set
  for k in "${lang_keys[@]}"; do
    lang_set["$k"]=1
  done

  missing=()
  extra=()
  for k in "${reference_keys[@]}"; do
    [[ -z "${lang_set[$k]:-}" ]] && missing+=("$k")
  done
  for k in "${lang_keys[@]}"; do
    [[ -z "${reference_set[$k]:-}" ]] && extra+=("$k")
  done

  if (( ${#missing[@]} > 0 )) || (( ${#extra[@]} > 0 )); then
    echo "✗ $name: out of sync with $reference"
    if (( ${#missing[@]} > 0 )); then
      echo "    missing keys (${#missing[@]}):"
      for k in "${missing[@]}"; do
        echo "      - $k"
      done
    fi
    if (( ${#extra[@]} > 0 )); then
      echo "    extra keys (${#extra[@]}):"
      for k in "${extra[@]}"; do
        echo "      - $k"
      done
    fi
    status=1
  else
    echo "✓ $name: parity OK (${#lang_keys[@]} keys)"
  fi
done

exit "$status"
