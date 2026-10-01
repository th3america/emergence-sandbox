import hashlib
import json
import unittest

from evaluate_run_pair import evaluate_run_pair


def canon(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(canon(value).encode("utf-8")).hexdigest()


R1 = {
    "steps": [
        {
            "id": "delta",
            "op": "compare",
            "inputs": ["$left", "$right"],
            "params": {},
        }
    ],
    "output": "delta",
}

R2 = {
    "steps": [
        {
            "id": "old",
            "op": "normalize",
            "inputs": ["$left"],
            "params": {"fields": {"id": ["id"], "value": ["value"]}},
        },
        {
            "id": "new",
            "op": "normalize",
            "inputs": ["$right"],
            "params": {"fields": {"id": ["id"], "value": ["value"]}},
        },
        {
            "id": "delta",
            "op": "compare",
            "inputs": ["old", "new"],
            "params": {},
        },
    ],
    "output": "delta",
}


def receipt(
    run_id,
    *,
    goal="changes",
    description="Find material changes",
    condition="baseline",
    recipe=R1,
    left=None,
    right=None,
    output=None,
    expected=None,
    error=None,
    passed=True,
    source="ai-import",
    parent=None,
):
    left = [{"id": "a", "value": 1}] if left is None else left
    right = [{"id": "a", "value": 2}] if right is None else right
    expected = (
        {"added": [], "removed": [], "changed": ["a"]}
        if expected is None
        else expected
    )
    output = expected if output is None else output

    return {
        "id": run_id,
        "goal": goal,
        "goal_description": description,
        "condition": condition,
        "proposal": {
            "participant": "test participant",
            "missing_function": "compare records",
            "prediction": "detect changes",
            "dependency": "compare",
            "recipe": recipe,
        },
        "recipe_sha256": digest(recipe),
        "inputs": {"left": left, "right": right},
        "output": output,
        "expected": expected,
        "error": error,
        "passed": passed,
        "trace": [],
        "source": source,
        "parent_run": parent,
    }


class RunPairEvaluationTests(unittest.TestCase):

    def test_exact_recipe_replay(self):
        a = receipt("run-a")
        b = receipt("run-b", parent="run-a")

        evidence = evaluate_run_pair(a, b)

        kinds = {x["kind"] for x in evidence["observations"]}
        self.assertIn("exact_recipe_replay", kinds)
        self.assertEqual(evidence["relations"]["recipe"], "same")
        self.assertEqual(evidence["relations"]["environment"], "same")

    def test_changed_recipe_under_changed_environment_is_not_called_adaptation(self):
        a = receipt("run-a")

        b = receipt(
            "run-b",
            recipe=R2,
            condition="schema",
            right=[{"key": "a", "value": 2}],
            parent="run-a",
        )

        evidence = evaluate_run_pair(a, b)

        kinds = {x["kind"] for x in evidence["observations"]}
        self.assertIn("changed_recipe_changed_environment", kinds)

        joined_unknowns = " ".join(evidence["unknowns"]).lower()
        self.assertIn("adaptation is unresolved", joined_unknowns)

    def test_changed_goal_is_explicit(self):
        a = receipt("run-a")

        b = receipt(
            "run-b",
            goal="additions",
            description="Return only newly added ids",
            parent="run-a",
        )

        evidence = evaluate_run_pair(a, b)

        kinds = {x["kind"] for x in evidence["observations"]}
        self.assertIn("changed_goal", kinds)
        self.assertEqual(evidence["relations"]["goal"], "changed")

    def test_countercheck_removed_operation_records_dependency_evidence(self):
        a = receipt("run-a")

        b = receipt(
            "run-b",
            condition="ablation",
            error="Countercheck removed required operation: compare",
            passed=False,
            output=None,
            parent="run-a",
        )

        evidence = evaluate_run_pair(a, b)

        self.assertTrue(evidence["countercheck"]["detected"])
        self.assertEqual(
            evidence["countercheck"]["effect"],
            "removed_operation_blocked_execution",
        )
        self.assertEqual(
            evidence["countercheck"]["removed_operation"],
            "compare",
        )

        # Critically: the evaluator still does not claim self-prompting.
        self.assertTrue(
            any(
                "Self-prompting is unresolved" in x
                for x in evidence["unknowns"]
            )
        )


if __name__ == "__main__":
    unittest.main()

