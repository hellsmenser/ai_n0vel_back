import asyncio
from core.db.mongo_client import get_mongo_collection
from core.logger import setup_logging
from core.task_manager import run_task_manager
from core import logger

log = logger.get_logger(__name__)


async def main():
    setup_logging()
    tasks = get_mongo_collection("tasks")
    log.info("orchestrator started")
    await run_task_manager(tasks)


if __name__ == "__main__":
    asyncio.run(main())
