from pymongo import MongoClient

from config.env import get_mongo_db_name, get_mongo_uri


def get_mongo_collection(name: str):
    client = MongoClient(get_mongo_uri())
    db = client[get_mongo_db_name()]
    return db[name]
