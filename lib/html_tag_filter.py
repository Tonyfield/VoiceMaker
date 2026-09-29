from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias
import re

import yaml


HTMLTagFilterDefinitions: TypeAlias = MappingABC[str, str]


@dataclass(frozen=True)
class HTMLTagFilterRule:
    name: str
    pattern: re.Pattern[str]


class HTMLTagFilter:
    def __init__(self, rules: Sequence[HTMLTagFilterRule]) -> None:
        self._rules = tuple(rules)

    def filter(self, text: str) -> str:
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        for rule in self._rules:
            text = rule.pattern.sub("", text)
        return text


class HTMLTagFilterFactory:
    def __init__(self) -> None:
        self._registry: dict[str, HTMLTagFilterRule] = {}

    def register(self, name: str, pattern: str) -> None:
        rule = self._compile_rule(name, pattern)
        self._registry[rule.name] = rule

    def list_filters(self) -> list[str]:
        return list(self._registry)

    def create_filter(self, names: Sequence[str]) -> HTMLTagFilter:
        return HTMLTagFilter(self._registry[name] for name in names)

    def load_filters(self, path: str | Path) -> list[str]:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

        if not isinstance(data, MappingABC):
            raise ValueError("filter configuration must be a mapping")

        compiled_rules = [self._compile_rule(name, pattern) for name, pattern in data.items()]
        for rule in compiled_rules:
            self._registry[rule.name] = rule
        return [rule.name for rule in compiled_rules]

    @staticmethod
    def _compile_rule(name: str, pattern: str) -> HTMLTagFilterRule:
        if not isinstance(name, str):
            raise ValueError("filter name must be a string")

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("filter name must be a string")

        if not isinstance(pattern, str):
            raise ValueError("filter pattern must be a string")

        try:
            compiled_pattern = re.compile(pattern, re.DOTALL)
        except re.error as error:
            raise ValueError(str(error)) from error

        return HTMLTagFilterRule(name=normalized_name, pattern=compiled_pattern)