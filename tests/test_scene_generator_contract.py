import unittest
from unittest.mock import patch
import sys
import types
import tempfile
from pathlib import Path
from copy import deepcopy
import json

from core.scene_generator import generate_scene

if "bson" not in sys.modules:
    bson_stub = types.ModuleType("bson")
    bson_stub.ObjectId = lambda value: value
    sys.modules["bson"] = bson_stub

from core.task_manager import handle_ready_to_generate
from core.task_manager import handle_ready_to_compile
from core.scene_contract import SceneContractError, serialize_scene_v1, validate_scene_v1


ALLOWED_ACTIONS = {
    "line",
    "scene",
    "show",
    "animate",
    "transition",
    "pause",
    "jump",
    "return",
}


class SceneGeneratorContractTests(unittest.TestCase):
    def test_generated_scene_matches_v1_root_contract(self):
        scene = generate_scene("task-123")

        self.assertEqual(scene["schema_version"], 1)
        self.assertEqual(scene["scene_id"], "task-123")
        self.assertNotIn("id", scene)
        self.assertNotIn("scene", scene)
        self.assertNotIn("music", scene)
        self.assertIsInstance(scene["characters"], dict)
        self.assertEqual(set(scene["characters"]), {"lira", "kael"})
        self.assertIsInstance(scene["dialogue"], list)

    def test_generated_actions_are_supported_and_resolvable(self):
        scene = generate_scene("task-456")
        dialogue = scene["dialogue"]

        self.assertEqual(dialogue[0]["type"], "scene")
        self.assertIn(dialogue[0]["target"], {"bg_forest", "bg_tavern_interior"})
        self.assertEqual(dialogue[-1]["type"], "return")

        for action in dialogue:
            self.assertIn(action["type"], ALLOWED_ACTIONS)
            self.assertNotEqual(action["type"], "music")
            if action["type"] == "line":
                self.assertIn(action["speaker"], scene["characters"])
                self.assertIsInstance(action["text"], str)
            if action["type"] == "show":
                self.assertIn(
                    action["target"],
                    {"lira neutral", "kael serious"},
                )
            if action["type"] == "animate":
                self.assertEqual(action["target"], "lira neutral")
                self.assertEqual(action["effect"]["type"], "shake")
                self.assertIsInstance(action["effect"], dict)
            if action["type"] == "jump":
                self.assertIsInstance(action["target"], str)


class SceneContractParityTests(unittest.TestCase):
    def test_schema_version_requires_integer_not_float_or_boolean(self):
        for version in (1.0, True):
            scene = generate_scene("schema-type")
            scene["schema_version"] = version
            with self.assertRaises(SceneContractError, msg=f"schema_version={version!r}"):
                validate_scene_v1(scene)

    def test_malformed_discriminators_are_contract_errors(self):
        cases = [
            (0, "type", []),
            (3, "speaker", {}),
            (0, "target", []),
            (1, "target", {}),
            (5, "target", []),
            (5, "effect", {"type": []}),
            (8, "effect", []),
        ]
        for action_index, field, value in cases:
            scene = generate_scene("malformed-discriminator")
            if action_index == 5 and field == "effect":
                scene["dialogue"][action_index]["effect"] = value
            else:
                scene["dialogue"][action_index][field] = value
            with self.assertRaises(SceneContractError, msg=f"action {action_index} {field}"):
                validate_scene_v1(scene)

        scene = generate_scene("malformed-jump")
        scene["dialogue"].insert(-1, {"type": "jump", "target": {}})
        with self.assertRaises(SceneContractError, msg="jump target"):
            validate_scene_v1(scene)

    def test_empty_characters_and_dialogue_match_client_contract(self):
        scene = {
            "schema_version": 1,
            "scene_id": "empty-scene",
            "characters": {},
            "dialogue": [],
        }
        self.assertIs(validate_scene_v1(scene), scene)

    def test_transform_accepts_finite_alpha_and_unbounded_alignment(self):
        scene = generate_scene("transform-boundary")
        show = scene["dialogue"][1]
        show["transform"] = {"xalign": -5.0, "yalign": 3.0, "alpha": 1.5}
        validate_scene_v1(scene)
        show["transform"]["alpha"] = float("inf")
        with self.assertRaises(SceneContractError):
            validate_scene_v1(scene)

    def test_animate_boundaries_match_client_contract(self):
        scene = generate_scene("animate-boundary")
        animate = next(action for action in scene["dialogue"] if action["type"] == "animate")
        animate["effect"].update({"xoffset": 1, "duration": 2, "repeat": 20})
        validate_scene_v1(scene)

        for field, invalid in (("xoffset", 0), ("xoffset", 201), ("duration", 0), ("duration", 2.01)):
            invalid_scene = deepcopy(scene)
            invalid_animate = next(action for action in invalid_scene["dialogue"] if action["type"] == "animate")
            invalid_animate["effect"][field] = invalid
            with self.assertRaises(SceneContractError, msg=f"{field}={invalid}"):
                validate_scene_v1(invalid_scene)

    def test_rejects_unknown_action_and_global_string_overflow(self):
        scene = generate_scene("invalid-action")
        scene["dialogue"][0]["type"] = "music"
        with self.assertRaises(SceneContractError):
            validate_scene_v1(scene)

    def test_jump_requires_approved_production_label(self):
        scene = generate_scene("invalid-jump-label")
        scene["dialogue"].insert(-1, {"type": "jump", "target": "stage1_contract_jump_target"})
        with self.assertRaises(SceneContractError):
            validate_scene_v1(scene)

        scene["dialogue"][-2]["target"] = "start"
        with self.assertRaises(SceneContractError):
            validate_scene_v1(scene)

        scene["dialogue"][-2]["target"] = "next_scene"
        validate_scene_v1(scene)

    def test_publish_serialization_rejects_nonfinite_nested_metadata(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            scene = generate_scene("nonfinite-metadata")
            scene["metadata"] = {"nested": {"value": value}}
            with self.assertRaises(SceneContractError, msg=repr(value)):
                serialize_scene_v1(scene)

    def test_publish_serialization_rejects_scene_over_raw_byte_limit(self):
        scene = generate_scene("oversized-scene")
        scene["metadata"] = {"chunks": ["x" * 128 for _ in range(9000)]}
        with self.assertRaises(SceneContractError):
            serialize_scene_v1(scene)

        scene = generate_scene("metadata-overflow")
        scene["metadata"] = {"note": "x" * 4097}
        with self.assertRaises(SceneContractError):
            validate_scene_v1(scene)


class _FakeCollection:
    def __init__(self):
        self.calls = []

    def update_one(self, query, update):
        self.calls.append((query, update))

    @property
    def last_update(self):
        return self.calls[-1][1]["$set"]


class TaskManagerSceneIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_uses_task_id_as_scene_id(self):
        collection = _FakeCollection()
        task_id = "0123456789abcdef01234567"

        with patch("core.task_manager.generate_scene", return_value={}) as generate:
            await handle_ready_to_generate(collection, {"_id": task_id})

        generate.assert_called_once_with(task_id)


class CompileSceneTests(unittest.IsolatedAsyncioTestCase):
    task_id = "0123456789abcdef01234567"

    async def test_none_result_sets_structured_error_without_writing(self):
        collection = _FakeCollection()

        await handle_ready_to_compile(collection, {"_id": self.task_id, "result": None})

        self.assertEqual(collection.last_update["status"], "error")
        self.assertEqual(collection.last_update["error"]["code"], "scene_missing")
        self.assertNotIn("result", collection.last_update)

    async def test_invalid_action_or_resource_sets_structured_error(self):
        collection = _FakeCollection()
        invalid = generate_scene(self.task_id)
        invalid["dialogue"][0]["target"] = "bg_unknown"

        await handle_ready_to_compile(collection, {"_id": self.task_id, "result": invalid})

        self.assertEqual(collection.last_update["status"], "error")
        self.assertEqual(collection.last_update["error"]["code"], "scene_contract_invalid")

    async def test_write_or_replace_failure_sets_structured_error(self):
        collection = _FakeCollection()
        with tempfile.TemporaryDirectory() as temp_root:
            with patch("core.task_manager.os.getcwd", return_value=temp_root), patch(
                "core.task_manager.os.replace", side_effect=OSError("disk unavailable")
            ):
                await handle_ready_to_compile(
                    collection,
                    {"_id": self.task_id, "result": generate_scene(self.task_id)},
                )

        self.assertEqual(collection.last_update["status"], "error")
        self.assertEqual(collection.last_update["error"]["code"], "scene_write_failed")

    async def test_valid_scene_is_written_atomically_then_marked_done(self):
        collection = _FakeCollection()
        result = generate_scene(self.task_id)
        with tempfile.TemporaryDirectory() as temp_root:
            with patch("core.task_manager.os.getcwd", return_value=temp_root):
                await handle_ready_to_compile(
                    collection,
                    {"_id": self.task_id, "result": result},
                )

            output = Path(temp_root) / "Novel" / "game" / "scenes" / f"scene_{self.task_id}.json"
            self.assertTrue(output.is_file())
            self.assertFalse(list(output.parent.glob("*.tmp")))
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["scene_id"], self.task_id)
            self.assertEqual(output.read_bytes(), serialize_scene_v1(result))

        self.assertEqual(collection.last_update, {"status": "done"})

    async def test_mismatched_scene_id_sets_contract_error(self):
        collection = _FakeCollection()
        await handle_ready_to_compile(
            collection,
            {"_id": self.task_id, "result": generate_scene("another-task")},
        )
        self.assertEqual(collection.last_update["status"], "error")
        self.assertEqual(collection.last_update["error"]["code"], "scene_contract_invalid")

    async def test_malformed_result_sets_contract_error_not_type_error(self):
        collection = _FakeCollection()
        malformed = generate_scene(self.task_id)
        malformed["dialogue"][0]["target"] = []
        await handle_ready_to_compile(collection, {"_id": self.task_id, "result": malformed})
        self.assertEqual(collection.last_update["status"], "error")
        self.assertEqual(collection.last_update["error"]["code"], "scene_contract_invalid")

    async def test_nonfinite_metadata_sets_contract_error_before_writing(self):
        collection = _FakeCollection()
        result = generate_scene(self.task_id)
        result["metadata"] = {"nested": {"value": float("nan")}}
        await handle_ready_to_compile(collection, {"_id": self.task_id, "result": result})
        self.assertEqual(collection.last_update["status"], "error")
        self.assertEqual(collection.last_update["error"]["code"], "scene_contract_invalid")

    async def test_oversized_serialized_scene_sets_contract_error_before_writing(self):
        collection = _FakeCollection()
        result = generate_scene(self.task_id)
        result["metadata"] = {"chunks": ["x" * 128 for _ in range(9000)]}
        await handle_ready_to_compile(collection, {"_id": self.task_id, "result": result})
        self.assertEqual(collection.last_update["status"], "error")
        self.assertEqual(collection.last_update["error"]["code"], "scene_contract_invalid")


if __name__ == "__main__":
    unittest.main()
