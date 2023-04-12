from dataclasses import dataclass, field
#  from .test import Test


@dataclass
class TestsCriteria:
    names: set[str] = field(default_factory=set)
    exclude_names: set[str] = field(default_factory=set)
    fuzzy_names: list[str] = field(default_factory=list)
    fuzzy_exclude_names: set[str] = field(default_factory=set)
    include_groups: set[str] = field(default_factory=set)
    require_groups: set[str] = field(default_factory=set)
    exclude_groups: set[str] = field(default_factory=set)
    hidden_tests: bool = False
    __test__ = False

    def match(self, name: str, groups: list[str], hidden: bool) -> bool:
        if hidden and not self.hidden_tests:
            return False

        included = not self.names and not self.fuzzy_names and not self.include_groups
        if not included and name:
            if self.names and name in self.names:
                included = True
            elif self.fuzzy_names and any(fuzzy in name for fuzzy in self.fuzzy_names):
                included = True

        if not included and self.include_groups and self.include_groups.intersection(groups):
            included = True

        if not included:
            return False

        if self.exclude_names and name in self.exclude_names:
            return False

        if self.fuzzy_exclude_names and any(fuzzy in name for fuzzy in self.fuzzy_exclude_names):
            return False

        if self.require_groups and not self.require_groups.issubset(groups):
            return False

        if self.exclude_groups and self.exclude_groups.intersection(groups):
            return False
        return True

    def __str__(self) -> str:
        lines = []
        if self.names:
            lines.append(f"Explicity included tests - " + ", ".join(sorted(self.names)))
        if self.include_groups:
            lines.append(f"Included groups - " + ", ".join(sorted(self.include_groups)))
        if self.fuzzy_names:
            lines.append(f"Fuzzy included tests - " + ", ".join(sorted(self.fuzzy_names)))
        if self.exclude_names:
            lines.append(f"Explicity excluded tests - " + ", ".join(sorted(self.exclude_names)))
        if self.fuzzy_exclude_names:
            lines.append(f"Fuzzy excluded tests - " + ", ".join(sorted(self.fuzzy_exclude_names)))
        if self.exclude_groups:
            lines.append(f"Excluded groups - " + ", ".join(sorted(self.exclude_groups)))
        if self.require_groups:
            lines.append(f"Required groups - " + ", ".join(sorted(self.require_groups)))
        if not lines:
            ret = "Test criteria: All tests"
            if self.hidden_tests:
                ret += " (hidden included)"
            return ret
        lines.insert(0, "Test criteria:")
        if self.hidden_tests:
            lines.append("Hidden tests are included")
        return "\n" + "\n".join(lines)
