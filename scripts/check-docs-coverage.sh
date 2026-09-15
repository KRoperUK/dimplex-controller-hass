#!/usr/bin/env bash
# Fail when a user-visible surface exists in the integration but is not mentioned
# in the documentation.
#
# Crude string matching, deliberately. Every documentation gap this repository has
# actually shipped was of the form "a new thing exists, the docs never mentioned
# it" — a new action missing from the actions reference, new entities missing from
# the entity reference. Detecting that needs no parsing of prose.
#
# Checks:
#   1. every action in custom_components/dimplex/services.yaml appears in
#      docs/reference/actions.md
#   2. every entity translation_key in the platform modules appears in
#      docs/reference/entities.md
#   3. every CONF_* option constant appears in docs/reference/options.md
#
# This cannot tell whether the documentation is *correct*, only whether it is
# aware the thing exists. That is the failure mode worth automating; correctness
# still needs a human.
#
# Usage: scripts/check-docs-coverage.sh
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

component="custom_components/dimplex"
actions_doc="docs/reference/actions.md"
entities_doc="docs/reference/entities.md"
options_doc="docs/reference/options.md"

status=0

for f in "$component/services.yaml" "$actions_doc" "$entities_doc" "$options_doc"; do
  if [[ ! -f "$f" ]]; then
    echo "::error file=$f::required file is missing"
    status=1
  fi
done
[[ "$status" -eq 0 ]] || exit "$status"

report() {
  # report <file> <kind> <name> <where>
  echo "::error file=$4::$2 '$3' is not mentioned in $4"
  echo "  -> defined in $1" >&2
}

# Match a snake_case identifier against a documentation page. Succeeds on the
# literal identifier, or on a line containing every word of it — documentation
# writes prose ("Status poll interval"), not identifiers ("status_interval"), and
# may add words in between.
mentioned() {
  local name=$1 doc=$2
  grep -qi -- "$name" "$doc" && return 0
  local pattern=""
  for word in ${name//_/ }; do
    pattern+=".*${word}"
  done
  grep -qiE -- "$pattern" "$doc"
}

# --- 1. Actions -----------------------------------------------------------
# Top-level keys in services.yaml are the action names.
actions=$(grep -E '^[a-z_]+:' "$component/services.yaml" | sed 's/:.*//')
if [[ -z "$actions" ]]; then
  echo "::error file=$component/services.yaml::found no actions — has the format changed?"
  status=1
fi
for action in $actions; do
  if ! grep -q "$action" "$actions_doc"; then
    report "$component/services.yaml" "action" "dimplex.$action" "$actions_doc"
    status=1
  fi
done

# --- 2. Entity translation keys ------------------------------------------
# Matches both `translation_key="x"` and `_attr_translation_key = "x"`.
# repairs.py is excluded: its keys are repair issue ids, not entities.
keys=$(grep -rhoE '_?_?attr_?_?translation_key *= *"[a-z0-9_]+"|translation_key="[a-z0-9_]+"' \
  "$component"/binary_sensor.py "$component"/sensor.py "$component"/switch.py "$component"/climate.py \
  2>/dev/null | grep -oE '"[a-z0-9_]+"' | tr -d '"' | sort -u)
if [[ -z "$keys" ]]; then
  echo "::error file=$component::found no entity translation keys — has the format changed?"
  status=1
fi
for key in $keys; do
  if ! mentioned "$key" "$entities_doc"; then
    report "$component" "entity" "$key" "$entities_doc"
    status=1
  fi
done

# --- 3. Options -----------------------------------------------------------
# Only the options-flow constants: the auth/token ones are config-entry data and
# are documented as storage, not as options.
options=$(grep -oE '^CONF_(STATUS_INTERVAL|ENERGY_INTERVAL|BOOST_DURATION) *= *"[a-z_]+"' \
  "$component/const.py" | grep -oE '"[a-z_]+"' | tr -d '"' | sort -u)
for opt in $options; do
  if ! mentioned "$opt" "$options_doc"; then
    report "$component/const.py" "option" "$opt" "$options_doc"
    status=1
  fi
done

# --- 4. Version stamp -----------------------------------------------------
# The docs footer shows the integration version from zensical.toml, bumped by
# release-please. If that updater ever stops firing, the footer would quietly
# advertise an old version on every page — so assert it matches the manifest.
# `|| true` matters: under `set -euo pipefail` a grep that finds nothing would
# abort the script here, before the checks below could report anything useful.
manifest_version=$(grep -oE '"version" *: *"[^"]+"' "$component/manifest.json" | grep -oE '"[^"]+"$' | tr -d '"' || true)
docs_version=$(grep -oE '^integration_version *= *"[^"]+"' zensical.toml | grep -oE '"[^"]+"' | tr -d '"' || true)

if [[ -z "$manifest_version" ]]; then
  echo "::error file=$component/manifest.json::could not read a version — has the format changed?"
  status=1
fi
if [[ -z "$docs_version" ]]; then
  echo "::error file=zensical.toml::no integration_version — the docs footer stamp is missing"
  status=1
elif [[ "$docs_version" != "$manifest_version" ]]; then
  echo "::error file=zensical.toml::integration_version is $docs_version but manifest.json says $manifest_version"
  echo "  -> release-please should bump both; check the generic updater is configured for zensical.toml" >&2
  status=1
fi

if [[ "$status" -eq 0 ]]; then
  echo "✓ docs coverage OK"
  echo "  actions:  $(echo "$actions" | wc -w | tr -d ' ')"
  echo "  entities: $(echo "$keys" | wc -w | tr -d ' ')"
  echo "  options:  $(echo "$options" | wc -w | tr -d ' ')"
  echo "  version:  $docs_version (matches manifest)"
else
  echo "" >&2
  echo "See the annotated error(s) above. For a missing action, entity or option," >&2
  echo "a one-line table row on the named reference page is enough to pass." >&2
fi

exit "$status"
