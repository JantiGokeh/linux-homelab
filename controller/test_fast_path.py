import os
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault(
    "VAL_TOOLS_PATH",
    str(Path(__file__).resolve().parents[1] / "config" / "tools.json"),
)

import val_controller


class FastPathTests(unittest.TestCase):
    def test_owner_reference_correction(self):
        for text in ("I am Sir’s personal assistant.", "I am Sir's agent."):
            self.assertIn("Owner's", val_controller.correct_owner_reference(text))
        for text in ("Yes, Sir.", "How may I help, Sir?", "Sir Isaac Newton was a physicist.", "Sir's book"):
            self.assertEqual(val_controller.correct_owner_reference(text), text)

    @patch.object(val_controller, "log_operation")
    @patch.object(val_controller, "ask_model")
    @patch.object(val_controller, "run_tool")
    def test_weather_fast_path_does_not_call_model(self, run_tool, ask_model, _log):
        run_tool.return_value = {
            "ok": True,
            "condition": "Clear sky",
            "current": {"temperature_2m": 70},
            "hourly": [],
            "location": "New York, New York",
        }
        answer, timings, route = val_controller.answer_with_tools(
            "What's the weather now?", []
        )
        self.assertEqual(route, "deterministic")
        self.assertIn("70 degrees Fahrenheit", answer)
        self.assertIn("tool_ms", timings)
        ask_model.assert_not_called()

    @patch.object(val_controller, "log_operation")
    @patch.object(val_controller, "ask_model")
    @patch.object(val_controller, "run_tool")
    def test_fast_path_tool_failure_has_safe_answer(self, run_tool, ask_model, _log):
        run_tool.side_effect = TimeoutError()
        answer, _timings, route = val_controller.answer_with_tools(
            "What's on my calendar tomorrow?", []
        )
        self.assertEqual(route, "deterministic")
        self.assertIn("couldn't retrieve", answer)
        ask_model.assert_not_called()

    @patch.object(val_controller, "ask_model", return_value="Hello, Sir.")
    def test_non_tool_request_retains_model_fallback(self, ask_model):
        answer, timings, route = val_controller.answer_with_tools("Hello Val", [])
        self.assertEqual(answer, "Hello, Sir.")
        self.assertEqual(route, "model")
        self.assertIn("model_route_ms", timings)
        ask_model.assert_called_once()

    @patch.object(val_controller, "log_operation")
    @patch.object(val_controller, "ask_model")
    @patch.object(val_controller, "run_tool")
    def test_calendar_description_is_spoken_only_when_requested(self, run_tool, ask_model, _log):
        run_tool.return_value = {
            "ok": True,
            "count": 1,
            "events": [{
                "summary": "To do list",
                "all_day": True,
                "description": "Finish homework and study for the exam",
            }],
        }
        brief, _timings, route = val_controller.answer_with_tools(
            "What's on my calendar today?", []
        )
        detailed, _timings, detail_route = val_controller.answer_with_tools(
            "What's on my calendar today? Read the description.", []
        )
        self.assertEqual(route, "deterministic")
        self.assertEqual(detail_route, "deterministic")
        self.assertNotIn("Finish homework", brief)
        self.assertIn("Finish homework", detailed)
        ask_model.assert_not_called()

    @patch.object(val_controller, "log_operation")
    @patch.object(val_controller, "ask_model")
    @patch.object(val_controller, "run_tool")
    def test_calendar_description_followup_reuses_prior_date_request(self, run_tool, ask_model, _log):
        run_tool.return_value = {
            "ok": True,
            "count": 1,
            "events": [{
                "summary": "To do list",
                "all_day": True,
                "description": "Finish homework",
            }],
        }
        context = [
            {"role": "user", "content": "What's on my calendar tomorrow?"},
            {"role": "assistant", "content": "You have 1 event: To do list, all day."},
        ]
        answer, _timings, route = val_controller.answer_with_tools(
            "Read the description.", context
        )
        self.assertEqual(route, "deterministic")
        self.assertIn("Finish homework", answer)
        self.assertEqual(run_tool.call_args.args[0]["arguments"]["start_offset_days"], 1)
        ask_model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
