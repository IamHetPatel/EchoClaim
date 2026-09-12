"""Versioned prompt registry.

Every prompt is an artifact with a semver and a content hash. The agent loads
`jamie_system@<version>`; logs record which version produced each response, so a
quality change is always traceable to a prompt change. Loaded by the agent so every response is attributable to a prompt hash.

Prompts live as YAML in `llmops/prompts/<name>.<version>.yaml`:

    name: jamie_system
    version: "1.0.0"
    active: true
    template: |
      You are Jamie, a claims-intake specialist ...
      {known_context}
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class PromptVersion:
    name: str
    version: str
    template: str
    active: bool

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.template.encode()).hexdigest()[:12]

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}+{self.content_hash}"

    def render(self, **kwargs) -> str:
        return self.template.format(**kwargs)


class PromptRegistry:
    def __init__(self, prompts_dir: Path = PROMPTS_DIR):
        self.dir = Path(prompts_dir)

    def _load_all(self, name: str) -> list[PromptVersion]:
        import yaml

        out = []
        for f in sorted(self.dir.glob(f"{name}.*.yaml")):
            d = yaml.safe_load(f.read_text(encoding="utf-8"))
            out.append(PromptVersion(d["name"], str(d["version"]), d["template"], bool(d.get("active", False))))
        if not out:
            raise FileNotFoundError(f"no prompt files for '{name}' in {self.dir}")
        return out

    def get(self, name: str, version: str | None = None) -> PromptVersion:
        versions = self._load_all(name)
        if version:
            for v in versions:
                if v.version == version:
                    return v
            raise KeyError(f"{name}@{version} not found")
        active = [v for v in versions if v.active]
        if len(active) != 1:
            raise ValueError(f"expected exactly one active version of '{name}', found {len(active)}")
        return active[0]


registry = PromptRegistry()
