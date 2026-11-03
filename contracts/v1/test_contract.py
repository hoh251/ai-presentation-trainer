"""Regression checks for the shared contract, including invalid payloads."""
from __future__ import annotations

import copy
import unittest

import validate as contract


class ContractSchemaTests(unittest.TestCase):
    def test_fixture_flow_is_valid(self):
        for name in ("probe", "next", "retry", "retry_again", "incomplete", "finish"):
            contract.check(contract.fixtures["responses"][name], "answer_response")

    def test_answer_requires_state_version(self):
        value = copy.deepcopy(contract.fixtures["answer_requests"]["first"])
        del value["state_version"]
        with self.assertRaises(AssertionError):
            contract.check(value, "answer_request")

    def test_question_rejects_four_criteria(self):
        value = copy.deepcopy(contract.fixtures["questions"]["q1"])
        value["criteria"] *= 2
        with self.assertRaises(AssertionError):
            contract.check(value, "question")

    def test_response_rejects_invalid_action(self):
        value = copy.deepcopy(contract.fixtures["responses"]["probe"])
        value["agent_action"] = "pass_anyway"
        with self.assertRaises(AssertionError):
            contract.check(value, "answer_response")

    def test_response_rejects_wrong_state_type(self):
        value = copy.deepcopy(contract.fixtures["responses"]["probe"])
        value["state_version"] = "1"
        with self.assertRaises(AssertionError):
            contract.check(value, "answer_response")

    def test_report_requires_test_mode(self):
        value = copy.deepcopy(contract.fixtures["report"])
        del value["test_mode"]
        with self.assertRaises(AssertionError):
            contract.check(value, "report")

    def test_readiness_requires_question_service_status(self):
        value = copy.deepcopy(contract.fixtures["readiness"])
        del value["question_service_ready"]
        with self.assertRaises(AssertionError):
            contract.check(value, "readiness")


if __name__ == "__main__":
    unittest.main()
