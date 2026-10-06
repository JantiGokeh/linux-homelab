import json
import os
import re
from datetime import datetime
from pathlib import Path
from server_status import format_status
from discovery import format_discovery


TOOL_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
ALLOWED_VALUE_TYPES = {"string", "integer", "number", "boolean"}
DEFAULT_WEATHER_LOCATION = os.environ.get(
    "VAL_DEFAULT_WEATHER_LOCATION", "New York, New York"
)


class ToolRegistryError(ValueError):
    pass


class ToolRequestError(ValueError):
    pass


WEATHER_WORDS = re.compile(r"\b(weather|temperature|forecast)\b", re.IGNORECASE)
CALENDAR_WORDS = re.compile(
    r"\b(calendar|schedule|appointments?|events?|to[ -]?do(?: list)?)\b",
    re.IGNORECASE,
)
CALENDAR_DETAIL_WORDS = re.compile(
    r"\b(descriptions?|details?|what(?:'s| is) on (?:the|my) to[ -]?do(?: list)?)\b",
    re.IGNORECASE,
)
STATE_CHANGE_WORDS = re.compile(
    r"\b(add|book|cancel|change|create|delete|move|remove|reschedule|set|update)\b|\bschedule\s+(?:a|an|the)\b",
    re.IGNORECASE,
)


def deterministic_tool_request(message, registry):
    """Return a request for clear read-only intents, otherwise defer to the model."""
    if not isinstance(message, str):
        return None
    text = " ".join(message.strip().split())
    lowered = text.lower()

    if 'news.headlines' in registry and re.search(r'\b(news|headlines|top stories)\b', lowered) and not re.search(r'\b(?:history|historical|explain|define)\b', lowered):
        return {'type': 'tool_request', 'tool': 'news.headlines', 'arguments': {}}

    if 'web.search' in registry:
        match = re.search(r'\b(?:search(?: the)? web|web search|look (?:it|this|that|.+?) up online|find (?:.+? )?online)\b(?:\s+(?:for|about))?\s*(.*)', text, re.IGNORECASE)
        if match:
            query = match.group(1).strip(' .?!')
            if query:
                return {'type': 'tool_request', 'tool': 'web.search', 'arguments': {'query': query[:160]}}

    if 'server.status' in registry and re.search(
        r'\b(server|n8n|pi[ -]?hole|navidrome|containers?|cpu|ram|memory|disk|storage)\b', lowered
    ) and re.search(r'\b(status|doing|running|available|usage|used|free|space|healthy|health|how|check)\b', lowered) and not re.search(
        r'\b(restart|stop|start|delete|remove|install|update|create|explain|what is|what are)\b', lowered
    ):
        focus = []
        for key, pattern in {
            'cpu': r'\bcpu\b', 'memory': r'\b(?:ram|memory)\b',
            'disk': r'\b(?:disk|storage|space)\b', 'n8n': r'\bn8n\b',
            'pihole': r'\bpi[ -]?hole\b', 'navidrome': r'\bnavidrome\b',
            'val': r'\bval\b', 'services': r'\b(?:containers?|services?)\b',
        }.items():
            if re.search(pattern, lowered):
                focus.append(key)
        return {'type': 'tool_request', 'tool': 'server.status', 'arguments': {}, 'focus': focus}

    if (
        "weather.current" in registry
        and WEATHER_WORDS.search(text)
        and not re.search(r"\b(patterns?|climate|science|formation|explain|histor(?:y|ical))\b", lowered)
    ):
        location = DEFAULT_WEATHER_LOCATION
        location_match = re.search(
            r"\b(?:weather|temperature|forecast)\s+(?:in|for|at)\s+(.+?)(?:[?.!,]|\s+(?:today|now|right now|this (?:morning|afternoon|evening)))?$",
            text,
            re.IGNORECASE,
        )
        if location_match:
            candidate = re.sub(
                r"\s+(?:today|now|right now|this (?:morning|afternoon|evening))$",
                "", location_match.group(1), flags=re.IGNORECASE,
            ).strip(" ,.!?")
            if candidate and len(candidate) <= 120 and not re.fullmatch(r"(?:the\s+)?(?:next\s+)?[1-6]\s+hours?", candidate, re.IGNORECASE):
                location = candidate
        hours = 6
        hours_match = re.search(r"\b(?:next\s+)?([1-6])\s+hours?\b", lowered)
        if hours_match:
            hours = int(hours_match.group(1))
        return {
            "type": "tool_request",
            "tool": "weather.current",
            "arguments": {"location": location, "hours": hours},
            "include_forecast": bool(re.search(r"\b(forecast|hours?)\b", lowered)),
        }

    if (
        "calendar.events" in registry
        and CALENDAR_WORDS.search(text)
        and not STATE_CHANGE_WORDS.search(text)
    ):
        start_offset = 1 if re.search(r"\btomorrow\b", lowered) else 0
        days = 1
        days_match = re.search(r"\b(?:next\s+)?([1-9]|1[0-4])\s+days?\b", lowered)
        if days_match:
            days = int(days_match.group(1))
        elif re.search(r"\b(this|next) week\b", lowered):
            days = 7
        return {
            "type": "tool_request",
            "tool": "calendar.events",
            "arguments": {"start_offset_days": start_offset, "days": days},
            "direct_format": True,
            "include_descriptions": bool(CALENDAR_DETAIL_WORDS.search(text)),
        }

    return None


def _spoken_number(value):
    number = float(value)
    return str(int(round(number)))


def format_tool_result(tool_name, result, arguments):
    """Format small validated tool results without spending another model pass."""
    if tool_name == 'server.status':
        return format_status(result, arguments.get('_focus'))
    if tool_name in {'news.headlines', 'web.search'}:
        return format_discovery(result)
    if tool_name == "weather.current":
        current = result.get("current")
        if not isinstance(current, dict):
            raise ToolRequestError("weather result has no current conditions")
        condition = result.get("condition")
        temperature = current.get("temperature_2m")
        if not isinstance(condition, str) or not isinstance(temperature, (int, float)):
            raise ToolRequestError("weather result is incomplete")
        location = result.get("location") or arguments.get("location")
        answer = f"In {location}, it is {condition.lower()} and {_spoken_number(temperature)} degrees Fahrenheit."
        requested_hours = arguments.get("hours", 0) if arguments.get("_include_forecast") else 0
        hourly = result.get("hourly")
        if requested_hours and isinstance(hourly, list) and hourly:
            forecast_parts = []
            for entry in hourly[:requested_hours]:
                if not isinstance(entry, dict):
                    continue
                time_text = entry.get("time")
                entry_condition = entry.get("condition")
                entry_temperature = entry.get("temperature_2m")
                if not isinstance(time_text, str) or not isinstance(entry_condition, str) or not isinstance(entry_temperature, (int, float)):
                    continue
                try:
                    label = datetime.fromisoformat(time_text).strftime("%-I %p")
                except ValueError:
                    continue
                forecast_parts.append(
                    f"{label}: {entry_condition.lower()}, {_spoken_number(entry_temperature)} degrees"
                )
            if forecast_parts:
                answer += " The hourly forecast is " + "; ".join(forecast_parts) + "."
        return answer

    if tool_name == "calendar.events":
        events = result.get("events")
        count = result.get("count")
        if not isinstance(events, list) or not isinstance(count, int):
            raise ToolRequestError("calendar result is incomplete")
        range_name = "tomorrow" if arguments.get("start_offset_days") == 1 and arguments.get("days") == 1 else "that period"
        if count == 0:
            return f"You have no events scheduled {range_name}, Sir."
        event_parts = []
        include_descriptions = bool(arguments.get("_include_descriptions"))
        for event in events:
            if not isinstance(event, dict) or not isinstance(event.get("summary"), str):
                continue
            summary = event["summary"]
            if event.get("all_day"):
                event_text = f"{summary}, all day"
            else:
                start = event.get("start")
                if isinstance(start, str):
                    try:
                        event_text = f"{summary} at {datetime.fromisoformat(start).strftime('%-I:%M %p').replace(':00 ', ' ')}"
                    except ValueError:
                        event_text = summary
                else:
                    event_text = summary
            if include_descriptions:
                description = event.get("description")
                if isinstance(description, str) and description.strip():
                    event_text += f". Description: {description.strip()}"
                else:
                    event_text += ". It has no description"
            event_parts.append(event_text)
        if not event_parts:
            raise ToolRequestError("calendar result contains no usable events")
        return f"You have {count} event{'s' if count != 1 else ''}: " + "; ".join(event_parts) + "."

    raise ToolRequestError("tool has no deterministic formatter")


def load_tool_registry(path):
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ToolRegistryError(f"unable to load tool registry: {error}") from error

    if not isinstance(document, dict) or set(document) != {"version", "tools"}:
        raise ToolRegistryError("registry must contain only version and tools")
    if document["version"] != 1 or not isinstance(document["tools"], list):
        raise ToolRegistryError("unsupported registry format")

    registry = {}
    required_keys = {
        "name", "description", "endpoint", "timeout_seconds",
        "permission", "confirmation_required", "arguments",
    }
    for entry in document["tools"]:
        if not isinstance(entry, dict) or set(entry) != required_keys:
            raise ToolRegistryError("each tool must contain the exact registry fields")
        name = entry["name"]
        if not isinstance(name, str) or not TOOL_NAME_PATTERN.fullmatch(name):
            raise ToolRegistryError("invalid tool name")
        if name in registry:
            raise ToolRegistryError(f"duplicate tool: {name}")
        if not isinstance(entry["description"], str) or not entry["description"].strip():
            raise ToolRegistryError(f"{name}: description is required")
        if not isinstance(entry["endpoint"], str) or not entry["endpoint"].startswith("http://"):
            raise ToolRegistryError(f"{name}: endpoint must be a fixed HTTP URL")
        timeout = entry["timeout_seconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 120:
            raise ToolRegistryError(f"{name}: timeout must be between 1 and 120 seconds")
        if entry["permission"] not in {"read_only", "state_changing"}:
            raise ToolRegistryError(f"{name}: invalid permission")
        if not isinstance(entry["confirmation_required"], bool):
            raise ToolRegistryError(f"{name}: confirmation_required must be boolean")
        if entry["permission"] == "state_changing" and not entry["confirmation_required"]:
            raise ToolRegistryError(f"{name}: state-changing tools must require confirmation")
        if not isinstance(entry["arguments"], dict):
            raise ToolRegistryError(f"{name}: arguments must be an object")
        for argument_name, specification in entry["arguments"].items():
            if not isinstance(argument_name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", argument_name):
                raise ToolRegistryError(f"{name}: invalid argument name")
            if not isinstance(specification, dict) or set(specification) - {"type", "required", "max_length", "minimum", "maximum", "default"}:
                raise ToolRegistryError(f"{name}.{argument_name}: invalid argument schema")
            if specification.get("type") not in ALLOWED_VALUE_TYPES:
                raise ToolRegistryError(f"{name}.{argument_name}: invalid type")
            if not isinstance(specification.get("required"), bool):
                raise ToolRegistryError(f"{name}.{argument_name}: required must be boolean")
            if "max_length" in specification and (
                specification["type"] != "string"
                or isinstance(specification["max_length"], bool)
                or not isinstance(specification["max_length"], int)
                or not 1 <= specification["max_length"] <= 1000
            ):
                raise ToolRegistryError(f"{name}.{argument_name}: invalid max_length")
            if "default" in specification:
                default = specification["default"]
                expected = specification["type"]
                default_valid = {
                    "string": isinstance(default, str) and bool(default.strip()),
                    "integer": isinstance(default, int) and not isinstance(default, bool),
                    "number": isinstance(default, (int, float)) and not isinstance(default, bool),
                    "boolean": isinstance(default, bool),
                }[expected]
                if not default_valid:
                    raise ToolRegistryError(f"{name}.{argument_name}: invalid default")
            if "minimum" in specification or "maximum" in specification:
                if specification["type"] not in {"integer", "number"}:
                    raise ToolRegistryError(f"{name}.{argument_name}: numeric bounds require a numeric type")
                minimum = specification.get("minimum")
                maximum = specification.get("maximum")
                if (
                    isinstance(minimum, bool) or isinstance(maximum, bool)
                    or not isinstance(minimum, (int, float))
                    or not isinstance(maximum, (int, float))
                    or minimum > maximum
                ):
                    raise ToolRegistryError(f"{name}.{argument_name}: invalid numeric bounds")
        registry[name] = entry
    return registry


def parse_model_envelope(text, registry):
    try:
        envelope = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise ToolRequestError("model response is not valid JSON") from error
    if not isinstance(envelope, dict):
        raise ToolRequestError("model response must be a JSON object")

    response_type = envelope.get("type")
    if response_type == "answer":
        if set(envelope) != {"type", "message"}:
            raise ToolRequestError("answer contains unknown fields")
        if not isinstance(envelope["message"], str) or not envelope["message"].strip():
            raise ToolRequestError("answer message must be non-empty text")
        return {"type": "answer", "message": envelope["message"].strip()}

    if response_type != "tool_request":
        raise ToolRequestError("unknown response type")
    if set(envelope) != {"type", "tool", "arguments"}:
        raise ToolRequestError("tool request contains unknown fields")
    tool_name = envelope["tool"]
    if not isinstance(tool_name, str) or tool_name not in registry:
        raise ToolRequestError("tool is not registered")
    arguments = envelope["arguments"]
    if not isinstance(arguments, dict):
        raise ToolRequestError("arguments must be an object")

    schema = registry[tool_name]["arguments"]
    extras = set(arguments) - set(schema)
    if extras:
        raise ToolRequestError("unknown tool argument")
    normalized_arguments = dict(arguments)
    for name, specification in schema.items():
        if specification["required"] and name not in arguments:
            raise ToolRequestError(f"missing required argument: {name}")
        if name not in arguments and "default" in specification:
            normalized_arguments[name] = specification["default"]
        if name not in arguments:
            continue
        value = arguments[name]
        expected = specification["type"]
        valid = {
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
        }[expected]
        if not valid:
            raise ToolRequestError(f"invalid type for argument: {name}")
        if expected in {"integer", "number"}:
            if "minimum" in specification and value < specification["minimum"]:
                raise ToolRequestError(f"argument is below minimum: {name}")
            if "maximum" in specification and value > specification["maximum"]:
                raise ToolRequestError(f"argument is above maximum: {name}")
        if expected == "string":
            if not value.strip():
                raise ToolRequestError(f"argument must not be empty: {name}")
            if len(value) > specification.get("max_length", 1000):
                raise ToolRequestError(f"argument is too long: {name}")

    return {"type": "tool_request", "tool": tool_name, "arguments": normalized_arguments}
