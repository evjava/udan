#!/usr/bin/env bash
# Pre-commit hook to ban tuple annotations with 5+ elements.
# Catches: def foo(...) -> tuple[A, B, C, D, E, ...]

set -e

# Exemptions for the comma counter's blind spot: it counts every comma inside the
# annotation, so a nested tuple[...] counts as an extra element. Each listed
# path:line carries a real 4-element tuple plus one nested tuple[int, ...];
# drop the entry when the annotation goes.
EXEMPT_LINES=$(cat <<'EOF'
src/udan/core/impl_descriptor_factory.py:209
src/udan/core/impl_descriptor_factory.py:555
EOF
)

VIOLATIONS=$(grep -rn --include='*.py' 'tuple\[' src/udan/ \
    | while IFS= read -r line; do
        # Skip the exempted path:line entries listed above
        path="${line%%:*}"
        lineno="${line#*:}"
        lineno="${lineno%%:*}"
        if printf '%s\n' "$EXEMPT_LINES" | grep -qxF "$path:$lineno"; then
            continue
        fi
        # Check each tuple[...] match on the line individually
        echo "$line" | grep -oP 'tuple\[[^]]+\]' | while IFS= read -r match; do
            count=$(echo "$match" | tr -cd ',' | wc -c)
            if [ "$count" -ge 4 ]; then
                echo "  $line"
                break
            fi
        done
    done || true)

if [ -n "$VIOLATIONS" ]; then
    echo "Found tuple annotations with 5+ elements (use dataclass or NamedTuple instead):"
    echo "$VIOLATIONS"
    exit 1
fi

echo "No long-tuple violations"
