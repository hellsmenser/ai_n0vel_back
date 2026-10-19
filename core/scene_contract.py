"""Dependency-free mirror of the current Ren'Py scene contract v1."""

import json
import math

BACKGROUND_IMAGES = {"bg_forest", "bg_tavern_interior"}
CHARACTER_IMAGES = {
    "lira neutral", "lira sad", "lira angry", "lira smile",
    "kael neutral", "kael serious", "kael tired",
}
ALLOWED_ROOT_KEYS = {"schema_version", "scene_id", "name", "metadata", "characters", "dialogue"}
ALLOWED_ACTION_TYPES = {"line", "scene", "show", "animate", "transition", "pause", "jump", "return"}
MAX_DIALOGUE_ACTIONS = 500
MAX_CHARACTERS = 64
MAX_IDENTIFIER_LENGTH = 256
MAX_TEXT_LENGTH = 4000
MAX_GENERIC_STRING_LENGTH = 4096
MAX_SCENE_DEPTH = 20
MAX_SCENE_NODES = 10000
MAX_SCENE_RAW_BYTES = 1024 * 1024
PRODUCTION_JUMP_LABELS = {"next_scene"}
JSON_INDENT = 2
JSON_SEPARATORS = (",", ": ")


class SceneContractError(ValueError):
    """A stable, user-safe contract validation error."""


def _fail(message):
    raise SceneContractError(message)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _scan_scene_limits(root):
    """Iteratively apply the same structural limits as the Ren'Py client."""
    stack = [(root, "$", 1)]
    nodes = 0
    while stack:
        value, path, depth = stack.pop()
        nodes += 1
        if nodes > MAX_SCENE_NODES:
            _fail("scene exceeds node limit")
        if depth > MAX_SCENE_DEPTH:
            _fail("scene exceeds nesting depth")
        if isinstance(value, str):
            if len(value) > MAX_GENERIC_STRING_LENGTH:
                _fail(f"{path} string exceeds length limit")
        elif isinstance(value, list):
            for index in range(len(value) - 1, -1, -1):
                stack.append((value[index], f"{path}[{index}]", depth + 1))
        elif isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    _fail(f"{path} object key must be a string")
                if len(key) > MAX_GENERIC_STRING_LENGTH:
                    _fail(f"{path} object key exceeds length limit")
                stack.append((item, f"{path}.{key}", depth + 1))


def _require_keys(value, required, allowed, path):
    if not isinstance(value, dict):
        _fail(f"{path} must be an object")
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        _fail(f"{path} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        _fail(f"{path} has unsupported fields: {', '.join(sorted(unknown))}")


def _validate_identifier(value, path):
    if not isinstance(value, str) or not value or len(value) > MAX_IDENTIFIER_LENGTH:
        _fail(f"{path} must be a non-empty string up to {MAX_IDENTIFIER_LENGTH} characters")


def _validate_resource_target(value, path, resources, message):
    _validate_identifier(value, path)
    if value not in resources:
        _fail(message)


def _validate_transform(transform, path):
    _require_keys(transform, set(), {"xalign", "yalign", "alpha", "flip"}, path)
    for key in ("xalign", "yalign", "alpha"):
        if key in transform and not _is_number(transform[key]):
            _fail(f"{path}.{key} must be finite numeric")
    if "flip" in transform and not isinstance(transform["flip"], bool):
        _fail(f"{path}.flip must be boolean")


def _validate_action(action, index, characters):
    path = f"dialogue[{index}]"
    if not isinstance(action, dict):
        _fail(f"{path} must be an object")
    action_type = action.get("type")
    if not isinstance(action_type, str) or not action_type:
        _fail(f"{path}.type must be a non-empty string")
    if action_type not in ALLOWED_ACTION_TYPES:
        _fail(f"{path}.type is unsupported")
    common = {"type", "metadata"}
    if action_type == "line":
        _require_keys(action, {"type", "speaker", "text"}, common | {"speaker", "text"}, path)
        _validate_identifier(action["speaker"], f"{path}.speaker")
        if action["speaker"] not in characters:
            _fail(f"{path}.speaker is not declared")
        if not isinstance(action["text"], str) or len(action["text"]) > MAX_TEXT_LENGTH:
            _fail(f"{path}.text must be a string up to {MAX_TEXT_LENGTH} characters")
    elif action_type == "scene":
        _require_keys(action, {"type", "target"}, common | {"target"}, path)
        _validate_resource_target(
            action["target"], f"{path}.target", BACKGROUND_IMAGES,
            f"{path}.target is not a supported background",
        )
    elif action_type == "show":
        _require_keys(action, {"type", "target"}, common | {"target", "transform"}, path)
        _validate_resource_target(
            action["target"], f"{path}.target", CHARACTER_IMAGES,
            f"{path}.target is not a supported character image",
        )
        if "transform" in action:
            _validate_transform(action["transform"], f"{path}.transform")
    elif action_type == "animate":
        _require_keys(action, {"type", "target", "effect"}, common | {"target", "effect"}, path)
        _validate_resource_target(
            action["target"], f"{path}.target", CHARACTER_IMAGES,
            f"{path}.target is not a supported character image",
        )
        effect = action["effect"]
        _require_keys(effect, {"type"}, {"type", "xoffset", "duration", "repeat"}, f"{path}.effect")
        _validate_identifier(effect["type"], f"{path}.effect.type")
        if effect["type"] != "shake":
            _fail(f"{path}.effect.type is unsupported")
        if "xoffset" in effect and (not _is_number(effect["xoffset"]) or not 1 <= effect["xoffset"] <= 200):
            _fail(f"{path}.effect.xoffset must be a number from 1 to 200")
        if "duration" in effect and (not _is_number(effect["duration"]) or not 0 < effect["duration"] <= 2):
            _fail(f"{path}.effect.duration must be a number from 0 to 2")
        if "repeat" in effect and (not isinstance(effect["repeat"], int) or isinstance(effect["repeat"], bool) or not 1 <= effect["repeat"] <= 20):
            _fail(f"{path}.effect.repeat must be an integer from 1 to 20")
    elif action_type == "transition":
        _require_keys(action, {"type", "effect"}, common | {"effect"}, path)
        _validate_identifier(action["effect"], f"{path}.effect")
        if action["effect"] not in {"fade", "dissolve"}:
            _fail(f"{path}.effect is unsupported")
    elif action_type == "pause":
        _require_keys(action, {"type", "duration"}, common | {"duration"}, path)
        if not _is_number(action["duration"]) or not 0 <= action["duration"] <= 60:
            _fail(f"{path}.duration must be a number from 0 to 60")
    elif action_type == "jump":
        _require_keys(action, {"type", "target"}, common | {"target"}, path)
        _validate_identifier(action["target"], f"{path}.target")
        if action["target"] not in PRODUCTION_JUMP_LABELS:
            _fail(f"{path}.target is not an approved production label")
    else:
        _require_keys(action, {"type"}, common, path)
    if "metadata" in action and not isinstance(action["metadata"], dict):
        _fail(f"{path}.metadata must be an object")


def validate_scene_v1(scene):
    """Validate and return a v1 scene, or raise ``SceneContractError``."""
    _scan_scene_limits(scene)
    _require_keys(scene, {"schema_version", "scene_id", "characters", "dialogue"}, ALLOWED_ROOT_KEYS, "scene")
    if not isinstance(scene["schema_version"], int) or isinstance(scene["schema_version"], bool) or scene["schema_version"] != 1:
        _fail("scene.schema_version must be integer 1")
    _validate_identifier(scene["scene_id"], "scene.scene_id")
    if "name" in scene and not isinstance(scene["name"], str):
        _fail("scene.name must be a string")
    if "metadata" in scene and not isinstance(scene["metadata"], dict):
        _fail("scene.metadata must be an object")
    characters = scene["characters"]
    if not isinstance(characters, dict) or len(characters) > MAX_CHARACTERS:
        _fail(f"scene.characters must contain at most {MAX_CHARACTERS} entries")
    for key, value in characters.items():
        _validate_identifier(key, "scene.characters key")
        if not isinstance(value, str) or not value or len(value) > MAX_IDENTIFIER_LENGTH:
            _fail("scene.characters values must be non-empty strings up to 256 characters")
    dialogue = scene["dialogue"]
    if not isinstance(dialogue, list) or len(dialogue) > MAX_DIALOGUE_ACTIONS:
        _fail(f"scene.dialogue must contain at most {MAX_DIALOGUE_ACTIONS} actions")
    for index, action in enumerate(dialogue):
        _validate_action(action, index, characters)
    return scene


def serialize_scene_v1(scene):
    """Return the sole publish representation or raise ``SceneContractError``."""
    validate_scene_v1(scene)
    try:
        raw_bytes = json.dumps(
            scene,
            ensure_ascii=False,
            allow_nan=False,
            indent=JSON_INDENT,
            separators=JSON_SEPARATORS,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SceneContractError("scene is not JSON serializable") from error
    if len(raw_bytes) > MAX_SCENE_RAW_BYTES:
        _fail("serialized scene exceeds raw byte limit")
    return raw_bytes
