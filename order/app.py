import requests
import os
import atexit
from bson import ObjectId
from collections import Counter

from flask import Flask, jsonify
import pymongo

from payment_queue_dispatcher import PaymentQueueDispatcher

from time import sleep
import logging

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

sleep(10)
rpc = PaymentQueueDispatcher()


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

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


def close_db_connection():
    client.close()


gateway_url = os.environ["GATEWAY_URL"]

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
    if orders.delete_one({"_id": ObjectId(order_id)}).modified_count != 1:
        return jsonify({'error': f"Could not delete order {order_id}"})

    return jsonify({"success": True}), 200


@app.post('/addItem/<order_id>/<item_id>')
def add_item(order_id, item_id):
    # POST - adds a given item in the order given
    if orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$push": {"items": item_id}}
    ).modified_count != 1:
        return jsonify({'error': f"Could not add {item_id} to order {order_id}"}), 400

    return jsonify({"success": True}), 200


@app.delete('/removeItem/<order_id>/<item_id>')
def remove_item(order_id, item_id):
    # DELETE - removes the given item from the given order
    if orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$pull": {"items": item_id}}
    ).modified_count != 1:
        return jsonify({'error': f"Could not remove {item_id} to order {order_id}"}), 400

    return jsonify({"success": True}), 200


@app.get('/find/<order_id>')
def find_order(order_id):
    # GET - retrieves the information of an order (id, payment status, items included and user id)
    # Output JSON fields:
    # “order_id”  - the order’s id
    # “paid” (true/false)
    # “items”  - list of item ids that are included in the order
    # “user_id”  - the user’s id that made the order
    # “total_cost” - the total cost of the items in the order
    order = orders.find_one({"_id": ObjectId(order_id)})
    order_items = order["items"]

    total_cost = 0  # TODO this could def be made better
    for order_item in order_items:
        order_item_response = requests.get(
            f"{gateway_url}/stock/find/{order_item}")

        if order_item_response.status_code >= 400:
            return jsonify({"error": f"could not find item to calculate total cost!"}), 400

        total_cost += float(order_item_response.json()["price"])

    payment_resp = rpc.send_payment_status(
        str(order['user_id']), str(order['_id']))
    if not payment_resp['success']:
        return jsonify({"error": f"could not find payment status!"}), 400

    return {
        'order_id': str(order['_id']),
        'paid': payment_resp['paid'],
        'items': order['items'],
        'user_id': str(order['user_id']),
        'total_cost': total_cost
    }


@app.post('/checkout/<order_id>')
def checkout(order_id):
    # POST - makes the payment (via calling the payment service),
    # subtracts the stock (via the stock service)
    # and returns a status (success/failure).

    order = find_order(order_id)

    try:
        rpc.send_remove_credit(
            order['user_id'], order_id, float(order['total_cost']))
    except Exception as e:
        return jsonify({"error": f"could not pay"}), 400

    order_items = order["items"]

    order_items_counts = Counter(order_items)

    completed_items = []

    for order_item, count in order_items_counts.most_common():
        resp = requests.post(
            f"{gateway_url}/stock/subtract/{order_item}/{count}")
        if (resp.status_code >= 400):
            # Attempt to undo what has happened so far. Stock subtraction failed.
            refund_resp = undo_payment(order)
            stock_resp = undo_stock_update(completed_items)
            if refund_resp[1] >= 400 or stock_resp[1] >= 400:
                return jsonify({"error": f"could not undo. Refund Status Code: {refund_resp[1]}, StockUndo Status Code: {stock_resp[1]}"}), 400
            return jsonify({"error": f"check out failed due to insufficient funds or stock. successfully reverted"}), 444
        else:
            completed_items.append((order_item, count))

    return jsonify({"success": True}), 200


def make_payment(order):
    resp = requests.post(
        f"{gateway_url}/payment/pay/{order['user_id']}/{order['order_id']}/{order['total_cost']}")
    if (resp.status_code >= 400):
        return jsonify({"error": f"could not pay"}), resp.status_code
    else:
        return jsonify({"success": True}), 200


def undo_payment(order):
    resp = requests.post(
        f"{gateway_url}/payment/add_funds/{order['user_id']}/{order['total_cost']}")
    if (resp.status_code >= 400):
        return jsonify({"error": f"could not refund"}), resp.status_code
    else:
        return jsonify({"success": True}), 200


def undo_stock_update(completed_items):
    for completed_item, count in completed_items:
        resp = requests.post(
            f"{gateway_url}/stock/add/{completed_item}/{count}")
        if (resp.status_code >= 400):
            return jsonify({"error": f"could not subtract stock and Failed to rollback previous stock updates."}), 400
    return jsonify({"success": True}), 200
