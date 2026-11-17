"""Tiny example project: usages of the definitions."""

from example_math import example_add, example_scale


def run_report(base: int) -> int:
    total = example_add(base, example_scale(base, 2))
    return example_add(total, 1)
