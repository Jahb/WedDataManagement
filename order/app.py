import json
import os
import atexit
from bson import ObjectId

from flask import Flask, jsonify
import pymongo

import requests


gateway_url = os.environ['GATEWAY_URL']

app = Flask("order-service")

client: pymongo.MongoClient = pymongo.MongoClient(
    host=os.environ['MONGO_HOST'],
    port=int(os.environ['MONGO_PORT']),
    username=os.environ['MONGO_USERNAME'],
    password=os.environ['MONGO_PASSWORD'],
)

db = client["webDataManagement"]

orders = db["orders"]
order_barrier = db["order_barrier"]
cancel_order_barrier = db["cancel_order_barrier"]


def close_db_connection():
    db.close()


atexit.register(close_db_connection)


@app.post('/create/<user_id>')
def create_order(user_id):
    # POST - creates an order for the given user, and returns an order_id
    # Output JSON fields: “order_id”  - the order’s id
    order = {"user_id": user_id}
    orders.insert_one(order)

    return jsonify({
        "order_id": str(order['_id'])
    })


@app.delete('/remove/<order_id>')
def remove_order(order_id):
    # DELETE - deletes an order by ID
    if orders.delete_one({"_id" : ObjectId(order_id)}).modified_count != 1:
        return jsonify({'error' : f"Could not delete order {order_id}"})

    return jsonify({"success": True})


@app.post('/addItem/<order_id>/<item_id>')
def add_item(order_id, item_id):
    # POST - adds a given item in the order given
    if orders.update_one(
        {"_id" : ObjectId(order_id)},
        {"$push" : {"items" : item_id}}
    ).modified_count != 1:
        return jsonify({'error' : f"Could not add {item_id} to order {order_id}"})

    return jsonify({"success": True})


@app.delete('/removeItem/<order_id>/<item_id>')
def remove_item(order_id, item_id):
    # DELETE - removes the given item from the given order
    if orders.update_one(
        {"_id" : ObjectId(order_id)},
        {"$pull" : {"items" : item_id}}
    ).modified_count != 1:
        return jsonify({'error' : f"Could not add {item_id} to order {order_id}"})

    return jsonify({"success": True})



@app.get('/find/<order_id>')
def find_order(order_id):
    # GET - retrieves the information of an order (id, payment status, items included and user id)
    # Output JSON fields:
        # “order_id”  - the order’s id
        # “paid” (true/false)
        # “items”  - list of item ids that are included in the order
        # “user_id”  - the user’s id that made the order
        # “total_cost” - the total cost of the items in the order
    pass


@app.post('/checkout/<order_id>')
def checkout(order_id):
    # POST - makes the payment (via calling the payment service), subtracts the stock (via the stock service) and returns a status (success/failure).
    pass
