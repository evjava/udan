#!/bin/bash
# Count lines in Python source files using udan.
# Usage: tools/udan-count-lines.sh

cd "$(dirname "$0")/.."

# Lines of *.py matching pattern anywhere under dir (excluding __pycache__).
# Concatenating first keeps wc from printing its own `total` line, which the
# previous `wc -l {} +` + awk version double-counted.
count_lines() {
    local dir="$1"
    local pattern="$2"
    find "$dir" -name "$pattern" -type f -not -path '*/__pycache__/*' -print0 2>/dev/null \
        | xargs -0 -r cat 2>/dev/null | wc -l
}

# Same, but only for files directly inside dir (no subpackages).
count_lines_top() {
    local dir="$1"
    local pattern="$2"
    find "$dir" -maxdepth 1 -name "$pattern" -type f -print0 2>/dev/null \
        | xargs -0 -r cat 2>/dev/null | wc -l
}

# Tests
tests_lines=$(count_lines ./tests '*.py')

# src/udan: all packages, then broken down into subpackages and top-level prefixes
udan_total=$(count_lines ./src/udan '*.py')

udan_subs=""
udan_subs_sum=0
for sub_dir in ./src/udan/*/; do
    case "$sub_dir" in *__pycache__*) continue ;; esac
    [ -d "$sub_dir" ] || continue
    lines=$(count_lines "$sub_dir" '*.py')
    udan_subs_sum=$((udan_subs_sum + lines))
    udan_subs+="$(printf '\t\t\t%s/\t%s' "$(basename "$sub_dir")" "$lines")"$'\n'
done

api_lines=$(count_lines_top ./src/udan 'api_*.py')
impl_lines=$(count_lines_top ./src/udan 'impl_*.py')
plugins_lines=$(count_lines_top ./src/udan 'plugins_*.py')
utils_lines=$(count_lines_top ./src/udan 'utils_*.py')
io_lines=$(count_lines_top ./src/udan 'io_*.py')

# Top-level files matching none of the prefixes (config.py, plugins_system.py, __init__.py)
other_lines=$((udan_total - udan_subs_sum - api_lines - impl_lines - plugins_lines - utils_lines - io_lines))

# All src/udan_plugins_* packages
src_total=$udan_total
plugins_output=""
for plugin_dir in ./src/udan_plugins_*/; do
    [ -d "$plugin_dir" ] || continue
    lines=$(count_lines "$plugin_dir" '*.py')
    src_total=$((src_total + lines))
    plugins_output+="$(printf '\t\tsrc/%s\t%s' "$(basename "$plugin_dir")" "$lines")"$'\n'
done

total=$((tests_lines + src_total))

# Output in the expected format
echo -e "total\t$total"
echo -e "\ttests\t$tests_lines"
echo -e "\tsrc\t$src_total"
echo -e "\t\tsrc/udan\t$udan_total"
printf '%s' "$udan_subs"
echo -e "\t\t\tapi_*\t$api_lines"
echo -e "\t\t\timpl_*\t$impl_lines"
echo -e "\t\t\tplugins_*\t$plugins_lines"
echo -e "\t\t\tutils_*\t$utils_lines"
echo -e "\t\t\tio_*\t$io_lines"
echo -e "\t\t\tother\t$other_lines"
printf '%s' "$plugins_output"
