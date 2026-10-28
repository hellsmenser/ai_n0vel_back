import unittest
from copy import deepcopy
import json
from pathlib import Path
import re
from unittest.mock import patch
import sys
import types

from core.scene_contract import SceneContractError, validate_scene_v1
from core.scene_generator import generate_scene

if "bson" not in sys.modules:
    bson_stub = types.ModuleType("bson")
    bson_stub.ObjectId = lambda value: value
    sys.modules["bson"] = bson_stub

from core.task_manager import handle_ready_to_compile, handle_ready_to_generate


_UI_OMITTED = object()


def _find_client_schema():
    workspace = Path(__file__).resolve().parents[2]
    candidates = (
        workspace / "Novel" / "game" / "schema" / "scene-v1.schema.json",
        workspace / "ai_n0vel" / "game" / "schema" / "scene-v1.schema.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _schema_accepts_ui(scene, schema):
    """Evaluate the deliberately small ui schema without a runtime dependency."""
    if "ui" not in scene:
        return True
    ui = scene["ui"]
    ui_schema = schema["$defs"]["ui"]
    if not isinstance(ui, dict):
        return False
    properties = ui_schema["properties"]
    if ui_schema.get("additionalProperties") is False and set(ui) - set(properties):
        return False
    for key, value in ui.items():
        field_schema = properties[key]
        if "$ref" in field_schema:
            field_schema = schema["$defs"][field_schema["$ref"].rsplit("/", 1)[-1]]
        if field_schema.get("type") == "string" and not isinstance(value, str):
            return False
        if len(value) < field_schema.get("minLength", 0):
            return False
        if len(value) > field_schema.get("maxLength", len(value)):
            return False
        if "pattern" in field_schema and re.fullmatch(field_schema["pattern"], value) is None:
            return False
    return True


class _FakeCollection:
    def __init__(self):
        self.calls = []

    def update_one(self, query, update):
        self.calls.append((query, update))

    @property
    def last_update(self):
        return self.calls[-1][1]["$set"]


class SceneUiContractTests(unittest.TestCase):
    def test_ui_is_optional_and_omitted_by_legacy_generator_call(self):
        scene = generate_scene("legacy-task")

        self.assertNotIn("ui", scene)
        self.assertIs(validate_scene_v1(scene), scene)

    def test_all_ui_preferences_are_optional_bounded_identifiers(self):
        for ui in (
            {},
            {"theme_id": "literary"},
            {"palette_id": "warm_parchment"},
            {"font_pack_id": "editorial-serif-2"},
            {
                "theme_id": "future_theme_99",
                "palette_id": "unknown-palette",
                "font_pack_id": "font_2030",
            },
        ):
            scene = generate_scene("ui-task", ui=ui)
            self.assertEqual(scene["ui"], ui)
            self.assertIsNot(scene["ui"], ui)
            self.assertIs(validate_scene_v1(scene), scene)

    def test_malformed_ui_is_rejected(self):
        malformed_values = (
            None,
            [],
            {"theme_id": ""},
            {"theme_id": "Literary"},
            {"theme_id": "../literary"},
            {"theme_id": "a" * 65},
            {"palette_id": 42},
            {"font_pack_id": float("nan")},
            {"theme_id": "literary", "future": "field"},
            {"theme_id": {"nested": "literary"}},
        )

        for ui in malformed_values:
            scene = generate_scene("invalid-ui")
            scene["ui"] = ui
            with self.assertRaises(SceneContractError, msg=repr(ui)):
                validate_scene_v1(scene)

    def test_generator_does_not_alias_ui_input(self):
        ui = {"theme_id": "romantic", "palette_id": "dusty_rose"}
        expected = deepcopy(ui)

        scene = generate_scene("copy-ui", ui=ui)
        ui["theme_id"] = "mutated"

        self.assertEqual(scene["ui"], expected)


class SceneUiSchemaParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema_path = _find_client_schema()
        if schema_path is None:
            raise unittest.SkipTest(
                "cross-repo parity requires a sibling Novel or ai_n0vel client checkout"
            )
        with schema_path.open(encoding="utf-8") as schema_file:
            cls.schema = json.load(schema_file)

    def test_schema_and_python_validator_share_ui_acceptance_corpus(self):
        self.assertNotIn("ui", self.schema["required"])
        self.assertEqual(
            self.schema["properties"]["ui"],
            {"$ref": "#/$defs/ui"},
        )
        self.assertEqual(self.schema["$defs"]["ui"]["type"], "object")
        self.assertIs(self.schema["$defs"]["ui"]["additionalProperties"], False)
        self.assertEqual(self.schema["$defs"]["uiIdentifier"]["type"], "string")

        corpus = (
            ("absent", _UI_OMITTED, True),
            ("empty", {}, True),
            (
                "all fields",
                {
                    "theme_id": "literary",
                    "palette_id": "warm_parchment",
                    "font_pack_id": "editorial-serif-2",
                },
                True,
            ),
            (
                "unknown valid ids",
                {
                    "theme_id": "future_theme_99",
                    "palette_id": "palette_2030",
                    "font_pack_id": "font-pack-77",
                },
                True,
            ),
            ("wrong ui type", [], False),
            ("wrong field type", {"theme_id": 42}, False),
            ("extra field", {"theme_id": "literary", "future": "value"}, False),
            ("invalid format", {"theme_id": "../Literary"}, False),
            ("64 character boundary", {"theme_id": "a" * 64}, True),
            ("65 character boundary", {"theme_id": "a" * 65}, False),
        )

        for name, ui, expected in corpus:
            with self.subTest(name=name):
                scene = generate_scene("schema-parity")
                if ui is not _UI_OMITTED:
                    scene["ui"] = ui

                schema_accepted = _schema_accepts_ui(scene, self.schema)
                try:
                    validate_scene_v1(scene)
                    python_accepted = True
                except SceneContractError:
                    python_accepted = False

                self.assertEqual(schema_accepted, expected)
                self.assertEqual(python_accepted, expected)
                self.assertEqual(schema_accepted, python_accepted)


class TaskUiWiringTests(unittest.IsolatedAsyncioTestCase):
    task_id = "0123456789abcdef01234567"

    async def test_legacy_task_keeps_legacy_generator_call(self):
        collection = _FakeCollection()

        with patch("core.task_manager.generate_scene", return_value={}) as generate:
            await handle_ready_to_generate(collection, {"_id": self.task_id})

        generate.assert_called_once_with(self.task_id)

    async def test_top_level_ui_is_supported_as_transition_fallback(self):
        collection = _FakeCollection()
        ui = {
            "theme_id": "lovecraft_biopunk",
            "palette_id": "abyssal_green",
            "font_pack_id": "organic_serif",
        }

        with patch("core.task_manager.generate_scene", return_value={}) as generate:
            await handle_ready_to_generate(
                collection,
                {"_id": self.task_id, "ui": ui},
            )

        generate.assert_called_once_with(self.task_id, ui=ui)

    async def test_canonical_payload_ui_has_priority_over_top_level_fallback(self):
        collection = _FakeCollection()
        canonical_ui = {
            "theme_id": "science_fiction",
            "palette_id": "cyan_violet",
        }

        with patch("core.task_manager.generate_scene", return_value={}) as generate:
            await handle_ready_to_generate(
                collection,
                {
                    "_id": self.task_id,
                    "payload": {
                        "prompt": "A station beyond Neptune",
                        "ui": canonical_ui,
                    },
                    "ui": {"theme_id": "romantic"},
                },
            )

        generate.assert_called_once_with(self.task_id, ui=canonical_ui)

    async def test_malformed_payload_ui_reaches_contract_error(self):
        generated_collection = _FakeCollection()
        malformed_ui = {"theme_id": "../invalid"}

        await handle_ready_to_generate(
            generated_collection,
            {
                "_id": self.task_id,
                "payload": {"ui": malformed_ui},
            },
        )

        generated = generated_collection.last_update
        self.assertEqual(generated["status"], "generated")
        self.assertEqual(generated["result"]["ui"], malformed_ui)

        compiled_collection = _FakeCollection()
        await handle_ready_to_compile(
            compiled_collection,
            {"_id": self.task_id, "result": generated["result"]},
        )

        self.assertEqual(compiled_collection.last_update["status"], "error")
        self.assertEqual(
            compiled_collection.last_update["error"]["code"],
            "scene_contract_invalid",
        )


if __name__ == "__main__":
    unittest.main()
