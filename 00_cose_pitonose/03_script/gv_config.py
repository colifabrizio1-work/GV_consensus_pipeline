from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

GV_ROOT = Path(r"\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus")
CONFIG_DIR = GV_ROOT / "00_cose_pitonose" / "02_config"
_TOKEN_RE = re.compile(r"\{([^{}]+)\}")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        out[full_key] = value
        if isinstance(value, dict):
            out.update(_flatten(value, full_key))
    return out


def _resolve_value(value: Any, lookup: dict[str, Any]) -> Any:
    if isinstance(value, str):
        current = value
        for _ in range(20):
            changed = False
            for token in _TOKEN_RE.findall(current):
                replacement = lookup.get(token)
                if isinstance(replacement, str):
                    current = current.replace("{" + token + "}", replacement)
                    changed = True
            if not changed:
                break
        return current
    if isinstance(value, list):
        return [_resolve_value(item, lookup) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_value(item, lookup) for key, item in value.items()}
    return value


def _resolve_all(config: dict[str, Any]) -> dict[str, Any]:
    resolved = config
    for _ in range(20):
        lookup = _flatten(resolved)
        new_resolved = _resolve_value(resolved, lookup)
        if new_resolved == resolved:
            return new_resolved
        resolved = new_resolved
    return resolved


def load_config() -> dict[str, Any]:
    paths = _load_json(CONFIG_DIR / "paths.json")
    datasets = _load_json(CONFIG_DIR / "datasets.json")
    pipeline = _load_json(CONFIG_DIR / "pipeline.json")
    return _resolve_all({**paths, **datasets, **pipeline})


def get_path(config: dict[str, Any], dotted_key: str) -> Path:
    value: Any = config
    for part in dotted_key.split("."):
        value = value[part]
    return Path(value)


if __name__ == "__main__":
    cfg = load_config()
    print(json.dumps(cfg["pipeline"], indent=2, ensure_ascii=False))
