"""Deliberately wrong boundary fixture for the same exported contract."""


def decide(example):
    return example['days'] < 30
