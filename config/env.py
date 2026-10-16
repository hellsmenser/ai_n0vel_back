import os

from dotenv import load_dotenv

load_dotenv()

def get_mongo_uri():
    return os.getenv("MONGO_URI")

def get_mongo_db_name():
    return os.getenv("MONGO_DB_NAME", "default_db")