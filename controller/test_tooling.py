import json
import tempfile
import unittest
from pathlib import Path

from tooling import (
    ToolRegistryError, ToolRequestError, deterministic_tool_request,
    format_tool_result, load_tool_registry, parse_model_envelope,
)


WEATHER_TOOL = {
    "name": "weather.current",
    "description": "Get current weather for a supplied location.",
    "endpoint": "http://n8n:5678/webhook/val/weather/current",
    "timeout_seconds": 10,
    "permission": "read_only",
    "confirmation_required": False,
    "arguments": {
        "location": {"type": "string", "required": True, "max_length": 120}
    },
}


class ToolingTests(unittest.TestCase):
    def load(self, tools):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tools.json"
            path.write_text(json.dumps({"version": 1, "tools": tools}), encoding="utf-8")
            return load_tool_registry(path)

    def test_valid_answer(self):
        parsed = parse_model_envelope('{"type":"answer","message":"Hello, Sir."}', {})
        self.assertEqual(parsed["message"], "Hello, Sir.")

    def test_valid_registered_tool(self):
        registry = self.load([WEATHER_TOOL])
        parsed = parse_model_envelope(
            '{"type":"tool_request","tool":"weather.current","arguments":{"location":"Baltimore"}}',
            registry,
        )
        self.assertEqual(parsed["tool"], "weather.current")

    def test_optional_argument_receives_configured_default(self):
        weather = json.loads(json.dumps(WEATHER_TOOL))
        weather["arguments"]["location"].update({
            "required": False,
            "default": "New York, New York",
        })
        registry = self.load([weather])
        parsed = parse_model_envelope(
            '{"type":"tool_request","tool":"weather.current","arguments":{}}',
            registry,
        )
        self.assertEqual(parsed["arguments"]["location"], "New York, New York")

    def test_numeric_argument_bounds_are_enforced(self):
        weather = json.loads(json.dumps(WEATHER_TOOL))
        weather["arguments"]["hours"] = {
            "type": "integer", "required": False, "minimum": 1,
            "maximum": 6, "default": 6,
        }
        registry = self.load([weather])
        for hours in (0, 7):
            with self.subTest(hours=hours), self.assertRaises(ToolRequestError):
                parse_model_envelope(json.dumps({
                    "type": "tool_request", "tool": "weather.current",
                    "arguments": {"location": "Boston", "hours": hours},
                }), registry)

    def test_unknown_tool_is_rejected(self):
        with self.assertRaisesRegex(ToolRequestError, "not registered"):
            parse_model_envelope(
                '{"type":"tool_request","tool":"server.delete","arguments":{}}', {}
            )

    def test_missing_extra_and_wrong_type_arguments_are_rejected(self):
        registry = self.load([WEATHER_TOOL])
        invalid = [
            '{"type":"tool_request","tool":"weather.current","arguments":{}}',
            '{"type":"tool_request","tool":"weather.current","arguments":{"location":"Baltimore","units":"F"}}',
            '{"type":"tool_request","tool":"weather.current","arguments":{"location":42}}',
        ]
        for response in invalid:
            with self.subTest(response=response), self.assertRaises(ToolRequestError):
                parse_model_envelope(response, registry)

    def test_state_changing_tool_without_confirmation_is_rejected(self):
        unsafe = dict(WEATHER_TOOL, name="server.restart", permission="state_changing")
        with self.assertRaisesRegex(ToolRegistryError, "must require confirmation"):
            self.load([unsafe])

    def test_clear_weather_request_uses_deterministic_route(self):
        registry = self.load([dict(
            WEATHER_TOOL,
            arguments={
                "location": {"type": "string", "required": False, "max_length": 120, "default": "New York, New York"},
                "hours": {"type": "integer", "required": False, "minimum": 1, "maximum": 6, "default": 6},
            },
        )])
        request = deterministic_tool_request("What's the weather in Baltimore now?", registry)
        self.assertEqual(request["tool"], "weather.current")
        self.assertEqual(request["arguments"]["location"], "Baltimore")
        self.assertFalse(request["include_forecast"])

    def test_weather_forecast_hours_are_bounded_and_detected(self):
        registry = {"weather.current": {}}
        request = deterministic_tool_request("Give me the forecast for the next 3 hours", registry)
        self.assertEqual(request["arguments"]["hours"], 3)
        self.assertTrue(request["include_forecast"])

    def test_read_only_calendar_request_uses_deterministic_route(self):
        registry = {"calendar.events": {}}
        request = deterministic_tool_request("What is on my schedule tomorrow?", registry)
        self.assertEqual(request["arguments"], {"start_offset_days": 1, "days": 1})

    def test_calendar_change_requests_defer_to_guarded_model_route(self):
        registry = {"calendar.events": {}}
        messages = [
            "Create a calendar event tomorrow",
            "Schedule an event on my calendar",
            "Cancel my appointment tomorrow",
        ]
        for message in messages:
            with self.subTest(message=message):
                self.assertIsNone(deterministic_tool_request(message, registry))

    def test_unrelated_request_defers_to_model(self):
        registry = {"weather.current": {}, "calendar.events": {}}
        self.assertIsNone(deterministic_tool_request("Tell me about cloud formation", registry))
        self.assertIsNone(deterministic_tool_request("Explain historical weather patterns", registry))

    def test_weather_result_formats_without_model(self):
        result = {
            "ok": True,
            "condition": "Partly cloudy",
            "current": {"temperature_2m": 72.4},
            "hourly": [{"time": "2026-09-13T14:00", "condition": "Clear sky", "temperature_2m": 74}],
        }
        answer = format_tool_result(
            "weather.current", result,
            {"location": "New York, New York", "hours": 1, "_include_forecast": False},
        )
        self.assertEqual(answer, "In New York, New York, it is partly cloudy and 72 degrees Fahrenheit.")

    def test_calendar_result_formats_empty_and_timed_events(self):
        empty = format_tool_result(
            "calendar.events", {"ok": True, "count": 0, "events": []},
            {"start_offset_days": 1, "days": 1},
        )
        self.assertEqual(empty, "You have no events scheduled tomorrow, Sir.")
        populated = format_tool_result(
            "calendar.events",
            {"ok": True, "count": 1, "events": [{"summary": "Dentist", "start": "2026-09-14T10:00:00-04:00", "all_day": False}]},
            {"start_offset_days": 1, "days": 1},
        )
        self.assertEqual(populated, "You have 1 event: Dentist at 10 AM.")


if __name__ == "__main__":
    unittest.main()
