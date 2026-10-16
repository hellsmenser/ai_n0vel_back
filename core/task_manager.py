import asyncio
import os
import json
from bson import ObjectId
from core import logger
from core.scene_generator import generate_scene

log = logger.get_logger(__name__)


async def handle_new(collection, task):
    log.info(f"{task['_id']}: new → ready_to_generate")
    await update_status(collection, task["_id"], "ready_to_generate")


async def handle_generated(collection, task):
    log.info(f"{task['_id']}: generated → ready_to_compile")
    await update_status(collection, task["_id"], "ready_to_compile")


async def handle_ready_to_generate(collection, task):
    task_id = task["_id"]

    collection.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": "generating"}}
    )
    log.info(f"{task_id}: ready_to_generate → generating")

    scene_json = generate_scene()

    collection.update_one(
        {"_id": ObjectId(task_id)},
        {
            "$set": {
                "status": "generated",
                "result": scene_json
            }
        }
    )

    log.info(f"{task_id}: generating → generated")


async def handle_ready_to_compile(collection, task):
    result = task.get("result")
    scene_dir = os.path.abspath(os.path.join(os.getcwd(), "Novel", "game", "scenes"))
    scene_path = os.path.join(scene_dir, f"scene_{task['_id']}.json")
    log.debug(f"handle_ready_to_compile: result is None? {result is None}, scene_dir: {scene_dir}, scene_path: {scene_path}")
    try:
        if result is not None:
            os.makedirs(scene_dir, exist_ok=True)
            with open(scene_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            log.info(f"File written: {scene_path}")
        else:
            log.warning(f"No result to write for task {task['_id']}")
    except Exception as e:
        log.error(f"Error writing file {scene_path}: {e}")
    collection.update_one(
        {"_id": ObjectId(task['_id'])},
        {"$set": {"result": scene_path}}
    )
    log.info(f"{task['_id']}: ready_to_compile → done")
    await update_status(collection, task["_id"], "done")


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
            with collection.watch(full_document='updateLookup') as stream:
                log.info("Change stream opened successfully.")
                for change in stream:
                    log.debug(f"Change event: {json.dumps(change, default=str, ensure_ascii=False)}")
                    if change["operationType"] not in ("insert", "update"):
                        continue

                    doc = change.get("fullDocument")
                    if not doc:
                        continue

                    status = doc.get("status")
                    action = ACTIONS.get(status)
                    if not action:
                        continue

                    await asyncio.create_task(action(collection, doc))
        except Exception as e:
            log.error(f"Change stream error: {e}")
            await asyncio.sleep(2)


async def update_status(collection, task_id, new_status):
    collection.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": new_status}}
    )
    log.debug(f"{task_id}: set {new_status}")
