"""Display-only translations; IDs, course codes and persisted data stay unchanged."""

import re
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QApplication

LANGUAGES = {"en": "English", "de": "Deutsch", "fr": "Français", "es": "Español", "sv": "Svenska"}
CATALOG = {}
for line in Path(__file__).with_name("locales.tsv").read_text(encoding="utf-8").splitlines():
    fields = [part.replace("\\n", "\n") for part in line.split("\t")]
    if len(fields) != 5:
        raise ValueError(f"Invalid translation row: {line}")
    CATALOG[fields[0]] = dict(zip(("de", "fr", "es", "sv"), fields[1:], strict=True))

_language = "en"
_qt_translator = None
_patterns = []
for source in CATALOG:
    if re.search(r"\{\d+\}", source):
        parts = re.split(r"(\{\d+\})", source)
        pattern = "".join(
            "(.+?)" if re.fullmatch(r"\{\d+\}", part) else re.escape(part) for part in parts
        )
        _patterns.append(
            (len(re.sub(r"\{\d+\}", "", source)), source, re.compile(pattern, re.DOTALL))
        )
_patterns.sort(reverse=True, key=lambda entry: entry[0])


def set_language(language):
    global _language, _qt_translator
    _language = language if language in LANGUAGES else "en"
    app = QApplication.instance()
    if app:
        if _qt_translator is not None:
            app.removeTranslator(_qt_translator)
        _qt_translator = QTranslator(app)
        if _language != "en" and _qt_translator.load(
            f"qtbase_{_language}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)
        ):
            app.installTranslator(_qt_translator)


def tr(source, *values):
    """Translate a source template, preserving supplied user data verbatim."""
    if _language == "en":
        translated = source.replace("Cykelfest", "Bike Party")
    else:
        translated = CATALOG.get(source, {}).get(_language, source)
    return translated.format(*values) if values else translated


def translate_message(message):
    """Localize English diagnostics emitted by background/domain code."""
    if message in CATALOG:
        return tr(message)
    if message.endswith("…") and message[:-1] in CATALOG:
        return tr(message[:-1]) + "…"
    for _, source, pattern in _patterns:
        match = pattern.fullmatch(message)
        if match:
            values = list(match.groups())
            # Only these arguments are semantic labels, never names or addresses.
            if source in (
                "{0}: invalid {1} stop.",
                "{0}: existing route contains an invalid {1} stop.",
                "{0}: existing routes require different stops at the same host during {1}.",
            ):
                values[1] = tr(values[1])
            elif (
                source in ("That host is away during {0}.", "Select an existing {0} stop.")
                or source == "Duplicate IDs in {0}."
            ):
                values[0] = tr(values[0])
            elif source == "{0}: {1} is a {2} stop":
                values[2] = tr(values[2])
            elif source in ("CSV row {0}: {1}", "{0}: existing route cannot be kept: {1}"):
                values[1] = translate_message(values[1])
            return tr(source, *values)
    for suffix in (
        " No more valid triples were found before the time limit or greedy search ended.",
        " Respect existing routes enabled.",
    ):
        if message.endswith(suffix):
            return translate_message(message[: -len(suffix)]) + tr(suffix)
    if match := re.fullmatch(r"([PSR]-?\d+): (.+)", message, re.DOTALL):
        detail = translate_message(match[2])
        if detail != match[2]:
            return match[1] + ": " + detail
    # A solver validation error can contain several independent diagnostics.
    for source in CATALOG:
        if source.startswith(("Route ", "Participant ", "Host already", "Empty route.")):
            message = message.replace(source, tr(source))
    return message


def translate_html(source):
    """Translate known text nodes while leaving markup and reference URLs intact."""
    return re.sub(r"(?<=>)[^<>]+(?=<)", lambda match: translate_message(match.group()), source)


def field_label(field):
    titles = {
        "name": "Name / pairing",
        "id": "ID",
        "route_id": "Route ID",
        "appetizer_stop_id": "Appetizer",
        "main_stop_id": "Main Dish",
        "dessert_stop_id": "Dessert",
        "minimum_segment_km": "Preferred minimum segment length (km)",
        "maximum_segment_km": "Preferred maximum segment length (km)",
        "safe_edit": "Safe Edit",
        "respect_existing_routes": "Respect existing routes",
        "warning_multipliers": "Project Warnings",
        "ignored_warnings": "Project Warnings",
        "minimize_warning_counts": "Project Warnings",
    }
    return tr(titles.get(field, field.replace("_", " ").title()))


def error_text(error):
    """Render validation details as translated guidance instead of library prose."""
    if isinstance(error.__cause__, ValidationError):
        prefix = str(error).split(":", 1)[0]
        return translate_message(prefix) + ":\n" + error_text(error.__cause__)
    if not isinstance(error, ValidationError):
        return translate_message(str(error))
    messages = []
    for detail in error.errors():
        kind, context = detail["type"], detail.get("ctx", {})
        if kind == "value_error":
            message = translate_message(str(context.get("error", detail["msg"])))
        elif kind in (
            "greater_than_equal",
            "less_than_equal",
            "greater_than",
            "less_than",
            "multiple_of",
            "string_too_short",
        ):
            template, key = {
                "greater_than_equal": ("Must be at least {0}.", "ge"),
                "less_than_equal": ("Must be at most {0}.", "le"),
                "greater_than": ("Must be greater than {0}.", "gt"),
                "less_than": ("Must be less than {0}.", "lt"),
                "multiple_of": ("Must be a multiple of {0}.", "multiple_of"),
                "string_too_short": ("Must contain at least {0} characters.", "min_length"),
            }[kind]
            message = tr(template, context[key])
        else:
            message = tr(
                {
                    "missing": "Required field.",
                    "float_parsing": "Enter a number.",
                    "float_type": "Enter a number.",
                    "int_parsing": "Enter a whole number.",
                    "int_type": "Enter a whole number.",
                    "bool_type": "Use true or false.",
                    "extra_forbidden": "Unknown field.",
                    "string_pattern_mismatch": "Value does not match the required format.",
                }.get(kind, "Invalid value.")
            )
        location = " / ".join(
            field_label(part) if isinstance(part, str) else str(part + 1) for part in detail["loc"]
        )
        messages.append(f"{location}: {message}" if location else message)
    return "\n".join(messages)
