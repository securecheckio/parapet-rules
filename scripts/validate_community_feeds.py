#!/usr/bin/env python3
"""Validate community rule feed JSON files.

Checks (aligned with parapet-core rule / feed types):
- Feed envelope: version, name, description, published_at (RFC 3339), source, rules;
  optional deprecated_rule_ids (unique strings).
- Per-feed: duplicate rule ids within one file; each rule shape (version, id, name, enabled, rule).
- Across all `community/*.json`: each rule `id` at most once (Parapet does not namespace
  rule ids; the string `id` is the global merge key. This repo keeps community ids unique;
  operators still override a community rule by defining the same `id` in another feed URL
  with a lower `priority` in config).
- rule.rule: action in {block, alert, pass}, non-empty message, conditions tree
  (simple / compound / flowbit), optional flowbits block.
- Operators match ComparisonOperator; community rule ids must match
  ^community-[a-z][a-z0-9-]*$ (prefix marks feeds from this repo; Parapet does not add it).
- Optional rule.metadata: if present must be a JSON object (any keys for authors/tools).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COMMUNITY = ROOT / "community"

# parapet/core/src/rules/types.rs — RuleAction + ComparisonOperator (serde snake_case / renames)
VALID_ACTIONS = frozenset({"block", "alert", "pass"})
VALID_OPERATORS = frozenset(
    {
        "equals",
        "not_equals",
        "greater_than",
        "less_than",
        "greater_than_or_equal",
        "less_than_or_equal",
        "in",
        "not_in",
        "contains",
        "isnotset",
        "exists",
    }
)

MAX_CONDITION_DEPTH = 64
RULE_ID_RE = re.compile(r"^community-[a-z][a-z0-9-]*$")


def die(msg: str) -> None:
    raise SystemExit(msg)


def check_published_at(s: Any, *, path: Path) -> None:
    if not isinstance(s, str) or not s.strip():
        die(f"{path}: published_at must be a non-empty string (RFC 3339)")
    t = s.strip()
    try:
        if t.endswith("Z"):
            datetime.fromisoformat(t.replace("Z", "+00:00"))
        else:
            datetime.fromisoformat(t)
    except ValueError:
        die(f"{path}: published_at is not valid RFC 3339 / ISO-8601: {t!r}")


def validate_simple_condition(cond: dict, *, path: str) -> None:
    allowed = {"field", "operator", "value"}
    extra = set(cond) - allowed
    if extra:
        die(f"{path}: unexpected keys in simple condition: {sorted(extra)}")
    if not isinstance(cond.get("field"), str) or not cond["field"].strip():
        die(f"{path}: condition.field must be a non-empty string")
    op = cond.get("operator")
    if not isinstance(op, str):
        die(f"{path}: condition.operator must be a string")
    op_n = op.lower()
    if op_n not in VALID_OPERATORS:
        die(f"{path}: unknown operator {op!r}; expected one of {sorted(VALID_OPERATORS)}")


def validate_flowbit_condition(cond: dict, *, path: str) -> None:
    allowed = {"flowbit", "within_seconds", "count_operator", "count_value"}
    extra = set(cond) - allowed
    if extra:
        die(f"{path}: unexpected keys in flowbit condition: {sorted(extra)}")
    fb = cond.get("flowbit")
    if not isinstance(fb, str) or not fb.strip():
        die(f"{path}: flowbit condition needs non-empty string 'flowbit'")
    ws = cond.get("within_seconds")
    if ws is not None and (not isinstance(ws, int) or ws < 0):
        die(f"{path}: within_seconds must be a non-negative int or null")
    cv = cond.get("count_value")
    if cv is not None and (not isinstance(cv, int) or cv < 0):
        die(f"{path}: count_value must be a non-negative int or null")
    co = cond.get("count_operator")
    if co is not None and not isinstance(co, str):
        die(f"{path}: count_operator must be a string or null")


def validate_condition(cond: Any, *, path: str, depth: int) -> None:
    if depth > MAX_CONDITION_DEPTH:
        die(f"{path}: conditions nested deeper than {MAX_CONDITION_DEPTH}")
    if not isinstance(cond, dict):
        die(f"{path}: condition must be a JSON object")

    is_flowbit = "flowbit" in cond
    compound_keys = ("all", "any", "not")
    is_compound = any(k in cond for k in compound_keys)
    is_simple = "field" in cond and "operator" in cond

    n_modes = sum([is_flowbit, is_compound, is_simple])
    if n_modes > 1:
        die(
            f"{path}: condition must be exactly one of "
            f"simple (field+operator), compound (all/any/not), or flowbit (flowbit); got mixed keys"
        )
    if n_modes == 0:
        die(
            f"{path}: condition must be simple (field+operator), compound (all/any/not), "
            f"or flowbit (flowbit)"
        )

    if is_flowbit:
        validate_flowbit_condition(cond, path=path)
        return
    if is_simple:
        validate_simple_condition(cond, path=path)
        return

    allowed = set(compound_keys)
    extra = set(cond) - allowed
    if extra:
        die(f"{path}: unexpected keys in compound condition: {sorted(extra)}")
    if "all" in cond:
        ch = cond["all"]
        if not isinstance(ch, list) or not ch:
            die(f"{path}: 'all' must be a non-empty array")
        for i, c in enumerate(ch):
            validate_condition(c, path=f"{path}.all[{i}]", depth=depth + 1)
    if "any" in cond:
        ch = cond["any"]
        if not isinstance(ch, list) or not ch:
            die(f"{path}: 'any' must be a non-empty array")
        for i, c in enumerate(ch):
            validate_condition(c, path=f"{path}.any[{i}]", depth=depth + 1)
    if "not" in cond:
        inner = cond["not"]
        validate_condition(inner, path=f"{path}.not", depth=depth + 1)
    if not ("all" in cond or "any" in cond or "not" in cond):
        die(f"{path}: compound condition has no all, any, or not")


def validate_flowbits_actions(obj: dict, *, path: str) -> None:
    allowed = {"scope", "set", "unset", "increment", "ttl_seconds"}
    extra = set(obj) - allowed
    if extra:
        die(f"{path}: unexpected keys in flowbits: {sorted(extra)}")
    sc = obj.get("scope", "perwallet")
    if isinstance(sc, str):
        sc_l = sc.lower()
        if sc_l not in ("perwallet", "global"):
            die(f"{path}: flowbits.scope must be 'perwallet' or 'global', not {sc!r}")
    else:
        die(f"{path}: flowbits.scope must be a string")
    for key in ("set", "unset", "increment"):
        if key not in obj:
            continue
        v = obj[key]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            die(f"{path}: flowbits.{key} must be an array of strings")
    if "ttl_seconds" in obj and obj["ttl_seconds"] is not None:
        ttl = obj["ttl_seconds"]
        if not isinstance(ttl, int) or ttl < 0:
            die(f"{path}: flowbits.ttl_seconds must be a non-negative int or null")


def validate_rule(rule: dict, *, path: str) -> None:
    required_top = {"version", "id", "name", "enabled", "rule"}
    missing = sorted(required_top - set(rule.keys()))
    if missing:
        die(f"{path}: rule missing keys {missing}: id={rule.get('id')!r}")

    rid = rule["id"]
    if not isinstance(rid, str) or not rid.strip():
        die(f"{path}: rule.id must be a non-empty string")
    if not RULE_ID_RE.match(rid):
        die(
            f"{path}: rule.id must match {RULE_ID_RE.pattern} "
            f"(lowercase start, letters, digits, hyphens): {rid!r}"
        )

    if not isinstance(rule["version"], str) or not rule["version"].strip():
        die(f"{path}: rule.version must be a non-empty string: id={rid!r}")
    if not isinstance(rule["name"], str) or not rule["name"].strip():
        die(f"{path}: rule.name must be a non-empty string: id={rid!r}")
    if not isinstance(rule["enabled"], bool):
        die(f"{path}: rule.enabled must be boolean: id={rid!r}")

    if "description" in rule and rule["description"] is not None:
        if not isinstance(rule["description"], str):
            die(f"{path}: rule.description must be string or omitted: id={rid!r}")
    if "tags" in rule:
        t = rule["tags"]
        if not isinstance(t, list) or not all(isinstance(x, str) for x in t):
            die(f"{path}: rule.tags must be an array of strings: id={rid!r}")
    if "metadata" in rule and rule["metadata"] is not None:
        if not isinstance(rule["metadata"], dict):
            die(f"{path}: rule.metadata must be an object: id={rid!r}")
    if "author" in rule and rule["author"] is not None:
        if not isinstance(rule["author"], str):
            die(f"{path}: rule.author must be a string or omitted: id={rid!r}")

    r = rule["rule"]
    if not isinstance(r, dict):
        die(f"{path}: rule.rule must be object: id={rid!r}")
    rule_allowed = {"action", "conditions", "message", "flowbits"}
    extra_r = set(r) - rule_allowed
    if extra_r:
        die(f"{path}: unexpected keys in rule.rule: {sorted(extra_r)}: id={rid!r}")
    for k in ("action", "conditions", "message"):
        if k not in r:
            die(f"{path}: rule.rule missing {k!r}: id={rid!r}")

    act = r["action"]
    if not isinstance(act, str) or act.lower() not in VALID_ACTIONS:
        die(
            f"{path}: rule.rule.action must be one of {sorted(VALID_ACTIONS)} "
            f"(case-insensitive): id={rid!r}"
        )
    msg = r["message"]
    if not isinstance(msg, str) or not msg.strip():
        die(f"{path}: rule.rule.message must be a non-empty string: id={rid!r}")

    validate_condition(r["conditions"], path=f"{path}.conditions", depth=0)

    if "flowbits" in r and r["flowbits"] is not None:
        if not isinstance(r["flowbits"], dict):
            die(f"{path}: rule.rule.flowbits must be an object or omitted: id={rid!r}")
        validate_flowbits_actions(r["flowbits"], path=f"{path}.flowbits")


def validate_feed(obj: dict, *, path: Path) -> None:
    required = ("version", "name", "description", "published_at", "source", "rules")
    for k in required:
        if k not in obj:
            die(f"{path}: feed missing key {k!r}")

    if not isinstance(obj["version"], str) or not obj["version"].strip():
        die(f"{path}: feed.version must be a non-empty string")
    for key in ("name", "description", "source"):
        if not isinstance(obj[key], str) or not obj[key].strip():
            die(f"{path}: feed.{key} must be a non-empty string")

    check_published_at(obj["published_at"], path=path)

    if not isinstance(obj["rules"], list) or not obj["rules"]:
        die(f"{path}: feed.rules must be a non-empty list")

    if "deprecated_rule_ids" in obj:
        dep = obj["deprecated_rule_ids"]
        if not isinstance(dep, list) or not all(isinstance(x, str) and x.strip() for x in dep):
            die(f"{path}: deprecated_rule_ids must be an array of non-empty strings")
        if len(dep) != len(set(dep)):
            die(f"{path}: deprecated_rule_ids contains duplicates")

    ids: list[str] = []
    for rule in obj["rules"]:
        if not isinstance(rule, dict):
            die(f"{path}: each rule must be a JSON object")
        validate_rule(rule, path=f"{path}#{rule.get('id')}")
        rid = rule["id"]
        if rid in ids:
            die(f"{path}: duplicate rule id {rid!r}")
        ids.append(rid)


def main() -> None:
    if not COMMUNITY.exists():
        die(f"Missing directory: {COMMUNITY}")

    json_files = sorted(COMMUNITY.glob("*.json"))
    if not json_files:
        die(f"No json files found in {COMMUNITY}")

    id_to_files: dict[str, list[str]] = {}

    for path in json_files:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            die(f"{path}: expected object")
        validate_feed(obj, path=path)

        for rule in obj["rules"]:
            rid = rule["id"]
            id_to_files.setdefault(rid, []).append(path.name)

    cross = {k: v for k, v in id_to_files.items() if len(v) > 1}
    if cross:
        lines = [f"  {rid}: {paths}" for rid, paths in sorted(cross.items())]
        die(
            "Duplicate rule id across community/*.json (each id must appear in exactly one file):\n"
            + "\n".join(lines)
        )

    print(f"OK: validated {len(json_files)} feeds")


if __name__ == "__main__":
    main()
