import os
import atexit

from flask import Flask
from flask import jsonify

import pymongo
from bson.objectid import ObjectId

app = Flask("stock-service")

client: pymongo.MongoClient = pymongo.MongoClient(
    host=os.environ['MONGO_HOST'],
    port=int(os.environ['MONGO_PORT']),
    username=os.environ['MONGO_USERNAME'],
    password=os.environ['MONGO_PASSWORD'],
)

db = client["webDataManagement"]

stock = db["stock"]


def close_db_connection():
    client.close()


atexit.register(close_db_connection)


# Create a new Item & return the ID
@app.post('/item/create/<price>')
def create_item(price: int):
    item = {"stock": 0, "price": price}
    stock.insert_one(item)
    item["_id"] = str(item["_id"])
    return item


@app.get('/find/<item_id>')
def find_item(item_id: str):
    item = stock.find_one({"_id": ObjectId(item_id)})
    item["_id"] = str(item["_id"])
    item["price"] = int(item["price"])
    item["stock"] = int(item["stock"])
    return item


@app.post('/add/<item_id>/<amount>')
def add_stock(item_id: str, amount: int):
    return jsonify(success=True) if stock.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": int(amount)}}).modified_count == 1 else jsonify({'error': 'Fail'}), 400


@app.post('/subtract/<item_id>/<amount>')
def remove_stock(item_id: str, amount: int):
    item = find_item(item_id)
    if item["stock"] < int(amount):
        return jsonify({'error': 'Fail'}), 400
    return jsonify(success=True) if stock.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": -int(amount)}}).modified_count == 1 else jsonify({'error': 'Fail'}), 400
