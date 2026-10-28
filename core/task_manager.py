import asyncio
import json
import os
import tempfile

from bson import ObjectId

from core import logger
from core.scene_contract import SceneContractError, serialize_scene_v1, validate_scene_v1
from core.scene_generator import generate_scene


log = logger.get_logger(__name__)


async def handle_new(collection, task):
    log.info(f"{task['_id']}: new -> ready_to_generate")
    await update_status(collection, task["_id"], "ready_to_generate")


async def handle_generated(collection, task):
    log.info(f"{task['_id']}: generated -> ready_to_compile")
    await update_status(collection, task["_id"], "ready_to_compile")


async def handle_ready_to_generate(collection, task):
    task_id = task["_id"]
    collection.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": "generating"}})
    log.info(f"{task_id}: ready_to_generate -> generating")

    payload = task.get("payload")
    # Canonical producers write generation inputs under payload. The top-level
    # key remains a transition fallback, but never overrides payload.ui.
    if isinstance(payload, dict) and "ui" in payload:
        scene_json = generate_scene(str(task_id), ui=payload["ui"])
    elif "ui" in task:
        scene_json = generate_scene(str(task_id), ui=task["ui"])
    else:
        scene_json = generate_scene(str(task_id))
    collection.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": "generated", "result": scene_json}},
    )
    log.info(f"{task_id}: generating -> generated")


def _set_compile_error(collection, task_id, code, message):
    collection.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": "error", "error": {"code": code, "message": message}}},
    )


async def handle_ready_to_compile(collection, task):
    """Persist only an already-valid v1 scene, then verify the written bytes."""
    task_id = task["_id"]
    result = task.get("result")
    if not isinstance(result, dict):
        _set_compile_error(collection, task_id, "scene_missing", "Generated scene result must be an object.")
        return
    try:
        serialized_scene = serialize_scene_v1(result)
        if result["scene_id"] != str(task_id):
            raise SceneContractError("scene.scene_id must equal the task id")
    except SceneContractError as error:
        _set_compile_error(collection, task_id, "scene_contract_invalid", str(error))
        return

    scene_dir = os.path.abspath(os.path.join(os.getcwd(), "Novel", "game", "scenes"))
    scene_path = os.path.join(scene_dir, f"scene_{task_id}.json")
    temporary_path = None
    try:
        os.makedirs(scene_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=scene_dir,
            prefix=f"scene_{task_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            temporary_file.write(serialized_scene)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, scene_path)
        temporary_path = None
        with open(scene_path, "rb") as scene_file:
            persisted_bytes = scene_file.read()
        persisted_scene = json.loads(persisted_bytes.decode("utf-8"))
        validate_scene_v1(persisted_scene)
        if persisted_scene["scene_id"] != str(task_id):
            raise SceneContractError("persisted scene id does not match task id")
    except (OSError, TypeError, ValueError, json.JSONDecodeError, SceneContractError) as error:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass
        log.error(f"Error writing file {scene_path}: {error}")
        _set_compile_error(
            collection,
            task_id,
            "scene_write_failed",
            "Unable to atomically persist and verify scene JSON.",
        )
        return

    collection.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": "done"}})
    log.info(f"{task_id}: ready_to_compile -> done")


ACTIONS = {
    "new": handle_new,
    "ready_to_generate": handle_ready_to_generate,
    "generated": handle_generated,
    "ready_to_compile": handle_ready_to_compile,
}


async def run_task_manager(collection):
    log.info("listening for task changes...")
    while True:
        try:
            with collection.watch(full_document="updateLookup") as stream:
                log.info("Change stream opened successfully.")
                for change in stream:
                    log.debug(f"Change event: {json.dumps(change, default=str, ensure_ascii=False)}")
                    if change["operationType"] not in ("insert", "update"):
                        continue
                    doc = change.get("fullDocument")
                    if not doc:
                        continue
                    action = ACTIONS.get(doc.get("status"))
                    if action:
                        await asyncio.create_task(action(collection, doc))
        except Exception as error:
            log.error(f"Change stream error: {error}")
            await asyncio.sleep(2)


async def update_status(collection, task_id, new_status):
    collection.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": new_status}})
    log.debug(f"{task_id}: set {new_status}")
