"""Compare two saved emergence-sandbox run receipts.

This module does not infer self-prompting, adaptation, or learning merely
because a run passed. It reports observable relations between receipts and
identifies a next experiment that could discriminate stronger claims.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json_equal(a: Any, b: Any) -> bool:
    # Avoid Python quirks such as True == 1.
    return _canonical(a) == _canonical(b)


def _recipe_hash_status(run: dict[str, Any]) -> str:
    """Check whether the receipt's recipe hash matches its stored recipe."""
    proposal = run.get("proposal")
    recorded = run.get("recipe_sha256")

    if not isinstance(proposal, dict) or "recipe" not in proposal:
        return "recipe_missing"

    if not isinstance(recorded, str) or not recorded:
        return "hash_missing"

    try:
        calculated = _digest(proposal["recipe"])
    except (TypeError, ValueError):
        return "recipe_not_canonical_json"

    return "match" if calculated == recorded else "mismatch"


def _goal_changed(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a.get("goal") != b.get("goal")
        or a.get("goal_description") != b.get("goal_description")
    )


def _inputs_changed(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return not _json_equal(a.get("inputs"), b.get("inputs"))


def _is_countercheck(run: dict[str, Any]) -> bool:
    if run.get("condition") == "ablation":
        return True

    source = run.get("source")
    if isinstance(source, str):
        lowered = source.lower()
        return "countercheck" in lowered or "ablation" in lowered

    return False


def evaluate_run_pair(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Return a compact JSON-safe evidence record for two run receipts."""

    if not isinstance(previous, dict) or not isinstance(current, dict):
        raise TypeError("run receipts must be objects")

    prev_hash = previous.get("recipe_sha256")
    curr_hash = current.get("recipe_sha256")

    recipe_known = (
        _recipe_hash_status(previous) == "match"
        and _recipe_hash_status(current) == "match"
        and
        isinstance(prev_hash, str)
        and bool(prev_hash)
        and isinstance(curr_hash, str)
        and bool(curr_hash)
    )

    recipe_same = recipe_known and prev_hash == curr_hash
    recipe_changed = recipe_known and prev_hash != curr_hash

    goal_changed = _goal_changed(previous, current)
    inputs_changed = _inputs_changed(previous, current)
    condition_changed = previous.get("condition") != current.get("condition")

    # Experimental environment includes the supplied fixture/input state and
    # condition label. Counterchecks are separately identified below.
    environment_changed = (inputs_changed or condition_changed
                           or not _json_equal(previous.get("disabled"), current.get("disabled"))
                           or not _json_equal(previous.get("tool_snapshot"), current.get("tool_snapshot"))
                           or not _json_equal(previous.get("expected"), current.get("expected")))

    exact_recipe_replay = (
        recipe_same
        and not goal_changed
        and not environment_changed
    )

    recipe_reuse_changed_environment = (
        recipe_same
        and not goal_changed
        and environment_changed
    )

    changed_recipe_changed_environment = (
        recipe_changed
        and not goal_changed
        and environment_changed
    )

    current_countercheck = _is_countercheck(current)

    observations: list[dict[str, Any]] = []
    unknowns: list[str] = []

    if exact_recipe_replay:
        observations.append({
            "kind": "exact_recipe_replay",
            "detail": (
                "Same recipe hash, goal, condition, and inputs were observed."
            ),
        })

    if recipe_reuse_changed_environment:
        observations.append({
            "kind": "recipe_reuse_changed_environment",
            "detail": (
                "The same recipe hash was used while the experimental "
                "environment changed."
            ),
        })

    if changed_recipe_changed_environment:
        observations.append({
            "kind": "changed_recipe_changed_environment",
            "detail": (
                "The goal remained stable while both recipe and experimental "
                "environment changed."
            ),
        })
        unknowns.append(
            "Whether the recipe change was useful adaptation is unresolved; "
            "the receipt pair alone does not show that the changed steps were "
            "caused by, or correctly targeted, the changed dependency."
        )

    if goal_changed:
        observations.append({
            "kind": "changed_goal",
            "detail": (
                "The goal or goal description changed between runs; direct "
                "performance comparison is not evidence of transfer by itself."
            ),
        })

    # Independently inspect the recorded pass claim.
    current_result_matches_expected = (
        all(k in current for k in ("output", "expected", "error"))
        and
        current.get("error") is None
        and _json_equal(current.get("output"), current.get("expected"))
    )

    if isinstance(current.get("passed"), bool):
        if current["passed"] != current_result_matches_expected:
            observations.append({
                "kind": "pass_flag_disagreement",
                "detail": (
                    "Recorded passed flag disagrees with direct "
                    "output/expected/error comparison."
                ),
            })

    countercheck: dict[str, Any] = {
        "detected": current_countercheck,
        "result": "not_applicable",
    }

    if current_countercheck:
        countercheck["result"] = "observed"
        countercheck["same_recipe"] = recipe_same
        countercheck["same_goal"] = not goal_changed
        countercheck["same_inputs"] = not inputs_changed

        error = current.get("error")
        prefix = "Countercheck removed required operation: "

        if isinstance(error, str) and error.startswith(prefix):
            removed = error[len(prefix):].strip()
            countercheck.update({
                "effect": "removed_operation_blocked_execution",
                "removed_operation": removed or None,
                "dependency_evidence": (
                    "The removed operation was required by this recipe's "
                    "executed path under this tested fixture."
                ),
            })
            observations.append({
                "kind": "countercheck_dependency_observed",
                "detail": (
                    f"Removing operation {removed!r} prevented this recipe "
                    "from executing."
                ),
            })

        elif not _json_equal(
            previous.get("output"),
            current.get("output"),
        ):
            countercheck.update({
                "effect": "output_changed_under_countercheck",
                "dependency_evidence": (
                    "Behavior changed under the countercheck, but this pair "
                    "alone does not establish which dependency caused it."
                ),
            })

        elif previous.get("error") != current.get("error"):
            countercheck.update({
                "effect": "error_state_changed_under_countercheck",
                "dependency_evidence": (
                    "Execution behavior changed under the countercheck."
                ),
            })

        else:
            countercheck.update({
                "effect": "no_observed_effect",
                "dependency_evidence": (
                    "This countercheck did not produce an observable output "
                    "or error difference in this pair."
                ),
            })

    # These properties require provenance beyond pass/fail.
    unknowns.extend([
        (
            "Self-prompting is unresolved: these receipts do not establish "
            "whether missing_function was generated by the participant or "
            "supplied by an operator/source."
        ),
        (
            "Method creation is unresolved unless provenance establishes that "
            "the participant generated the recipe rather than replaying or "
            "receiving it."
        ),
    ])

    if recipe_reuse_changed_environment:
        next_experiment = {
            "kind": "dependency_perturbation",
            "proposal": (
                "Change one dependency while preserving the same goal; "
                "observe whether the participant retains unaffected recipe "
                "steps and changes only the dependent portion."
            ),
        }

    elif changed_recipe_changed_environment:
        next_experiment = {
            "kind": "matched_ablation_or_holdout",
            "proposal": (
                "Run the old and new recipes against the same changed "
                "environment, then ablate the changed step. This separates "
                "useful adaptation from coincidental recipe variation."
            ),
        }

    elif goal_changed:
        next_experiment = {
            "kind": "same_function_new_goal",
            "proposal": (
                "Use a new goal that shares one underlying function and check "
                "whether the participant reuses only the relevant method "
                "component rather than replaying the entire prior recipe."
            ),
        }

    elif exact_recipe_replay:
        next_experiment = {
            "kind": "changed_dependency",
            "proposal": (
                "Perturb one environmental dependency while keeping the goal "
                "fixed. Exact replay should cease to be sufficient if that "
                "dependency matters."
            ),
        }

    elif current_countercheck:
        next_experiment = {
            "kind": "countercheck_replication",
            "proposal": (
                "Repeat the same countercheck on a second fixture to determine "
                "whether the observed dependency is fixture-specific."
            ),
        }

    else:
        next_experiment = {
            "kind": "controlled_pair",
            "proposal": (
                "Hold goal and environment fixed while changing one recipe "
                "dependency, or hold recipe fixed while changing one "
                "environmental dependency."
            ),
        }

    return {
        "previous_run": previous.get("id"),
        "current_run": current.get("id"),
        "relations": {
            "recipe": (
                "same"
                if recipe_same
                else "changed"
                if recipe_changed
                else "unknown"
            ),
            "goal": "changed" if goal_changed else "same",
            "environment": "changed" if environment_changed else "same",
            "inputs_changed": inputs_changed,
            "condition_changed": condition_changed,
            "parent_link": current.get("parent_run") == previous.get("id"),
        },
        "recipe_integrity": {
            "previous": _recipe_hash_status(previous),
            "current": _recipe_hash_status(current),
        },
        "observations": observations,
        "countercheck": countercheck,
        "unknowns": unknowns,
        "next_experiment": next_experiment,
    }

