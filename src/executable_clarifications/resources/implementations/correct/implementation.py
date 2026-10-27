"""Reviewed authored age-window fixture, separate from the predicate engine."""


def decide(example):
    return example['days'] <= 30
