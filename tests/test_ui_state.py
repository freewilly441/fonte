import unittest

from ui_state import UiError, UiStateMachine


class UiStateMachineTests(unittest.TestCase):
    def test_state_transitions_record_history(self):
        machine = UiStateMachine[list[int]]()
        machine.to_loading("Loading items")
        machine.to_success([1, 2, 3])

        self.assertEqual(machine.state.kind, "success")
        self.assertEqual(machine.history[:3], ["idle", "loading", "success"])

    def test_error_transition(self):
        machine = UiStateMachine[str]()
        machine.to_error(UiError(title="Oops", message="Failed", recovery_action="Retry", category="unknown"))

        self.assertEqual(machine.state.kind, "error")
        self.assertEqual(machine.history[-1], "error")

    def test_loading_success_error_retry_sequence(self):
        machine = UiStateMachine[list[int]]()
        machine.to_loading("Loading...")
        machine.to_success([1])
        machine.to_error(UiError(title="Oops", message="Try again", recovery_action="Retry", category="unknown"))
        machine.to_loading("Retrying...")
        machine.to_success([1, 2])

        self.assertEqual(
            machine.history,
            ["idle", "loading", "success", "error", "loading", "success"],
        )


if __name__ == "__main__":
    unittest.main()
