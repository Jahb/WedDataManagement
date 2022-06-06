from http import HTTPStatus
import os
import atexit
from fastapi import FastAPI, HTTPException

import pymongo
from bson.objectid import ObjectId
import logging

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

app = FastAPI(title="stock-service")

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
@app.post('/item/create/{price}')
def create_item(price: float):
    # POST - adds an item and its price, and returns its ID.
    # Output JSON fields:
    # “item_id” - the item’s id
    item = {"stock": 0, "price": price}
    stock.insert_one(item)
    item["_id"] = str(item["_id"])
    item["item_id"] = str(item["_id"])
    return item


@app.get('/find/{item_id}')
def find_item(item_id: str):
    # GET - returns an item’s availability and price.
    # Output JSON fields:
    # “stock” - the item’s stock
    # “price” - the item’s price
    item = stock.find_one({"_id": ObjectId(item_id)})
    item["_id"] = str(item["_id"])
    item["item_id"] = str(item["_id"])
    item["price"] = float(item["price"])
    item["stock"] = int(item["stock"])
    return item


@app.post('/add/{item_id}/{amount}')
def add_stock(item_id: str, amount: float):
    # POST - adds the given number of stock items to the item count in the stock
    modified_count = stock.update_one({"_id": ObjectId(item_id)}, {
                                      "$inc": {"stock": float(amount)}}).modified_count
    if int(modified_count) == 1:
        return {"done": True}
    raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY,
                        "add_stock could not complete")


@app.post('/subtract/{item_id}/{amount}')
def remove_stock(item_id: str, amount: float):
    # POST - subtracts an item from stock by the amount specified.
    # TODO - how will we make this idempotent?
    with client.start_session() as session:
        with session.start_transaction():
            item = find_item(item_id)
            if item["stock"] < float(amount):
                raise HTTPException(
                    HTTPStatus.PRECONDITION_FAILED, f"insufficient stock for item {item}")

            modified_count = stock.update_one({"_id": ObjectId(item_id)}, {
                                              "$inc": {"stock": -float(amount)}}).modified_count
            if int(modified_count) == 1:
                return {"done": True}
            raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY,
                                "add_stock could not complete")
