"""Suggest similar Makefile targets using Levenshtein distance."""

import sys


def levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            tmp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = tmp
    return dp[n]


def parse_targets(makefile: str = "Makefile") -> list[str]:
    targets: list[str] = []
    with open(makefile) as f:
        for line in f:
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                t = line.split(":")[0].strip()
                if t and not t.startswith(".") and t != t.upper():
                    targets.append(t)
    return targets


def _is_suggestible(goal: str, candidate: str, dist: int) -> bool:
    """Check if a candidate is close enough to suggest.

    Uses similarity ratio: 1 - dist/max_len. Requires ratio >= 0.55.
    Also requires absolute distance <= 5 to avoid wildly different matches.
    """
    max_len = max(len(goal), len(candidate))
    if max_len == 0:
        return False
    ratio = 1 - dist / max_len
    return ratio >= 0.55 and dist <= 5


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(0)

    goal = sys.argv[1]
    targets = parse_targets()

    scored = [(levenshtein(goal, t), t) for t in targets]
    # Filter to only suggestible candidates, then pick the closest
    suggestible = [(d, t) for d, t in scored if _is_suggestible(goal, t, d)]

    msg = f'make: *** No rule to make target "{goal}".'
    if suggestible:
        suggestible.sort()
        _, best = suggestible[0]
        msg += f' Did you mean "{best}"?'
    print(msg, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
