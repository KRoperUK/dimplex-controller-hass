#!/usr/bin/env bash
# Validate GitHub alert syntax in tracked Markdown.
#
# GitHub renders `> [!IMPORTANT]` as a coloured callout only when the marker is
# alone on its line inside a blockquote. Break either rule and there is no error
# anywhere — the marker just renders as literal text in an ordinary blockquote,
# which is how the README's unofficial-project notice shipped in #182 and stayed
# broken on the repository home page. Prettier 2.2.1 caused that one by joining
# the marker with the line below it; this check is formatter-independent so a
# hand-typed mistake is caught too.
#
# Usage: scripts/check-md-alerts.sh [file ...]
# With no arguments, checks every tracked *.md file.

set -euo pipefail

if [[ $# -gt 0 ]]; then
  files=("$@")
else
  mapfile -t files < <(git ls-files '*.md' '*.markdown')
fi

if [[ ${#files[@]} -eq 0 ]]; then
  echo "no Markdown files to check"
  exit 0
fi

status=0

for file in "${files[@]}"; do
  [[ -f "$file" ]] || continue
  # Fenced code blocks legitimately show broken examples, so track fences and
  # skip their contents.
  while IFS=$'\t' read -r lineno kind line; do
    case "$kind" in
      trailing)
        echo "::error file=$file,line=$lineno::GitHub alert marker is not alone on its line, so it renders as literal text"
        printf '  %s:%s: %s\n' "$file" "$lineno" "$line" >&2
        printf '  -> put the marker on its own line:\n     > [!NOTE]\n     > body text\n' >&2
        status=1
        ;;
      unquoted)
        echo "::error file=$file,line=$lineno::GitHub alert marker is not in a blockquote, so it renders as literal text"
        printf '  %s:%s: %s\n' "$file" "$lineno" "$line" >&2
        printf '  -> prefix the marker and every body line with "> "\n' >&2
        status=1
        ;;
    esac
  done < <(awk '
    /^[[:space:]]*(```|~~~)/ { fence = !fence; next }
    fence { next }
    # Marker followed by anything other than trailing whitespace.
    /^[[:space:]]*>[[:space:]]*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][[:space:]]*[^[:space:]]/ {
      printf "%d\ttrailing\t%s\n", NR, $0; next
    }
    # Marker at the start of a line with no blockquote prefix at all.
    /^[[:space:]]*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]/ {
      printf "%d\tunquoted\t%s\n", NR, $0; next
    }
  ' "$file")
done

if [[ "$status" -eq 0 ]]; then
  echo "✓ GitHub alert syntax OK (${#files[@]} file(s))"
else
  echo "" >&2
  echo "See https://docs.github.com/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#alerts" >&2
fi

exit "$status"
