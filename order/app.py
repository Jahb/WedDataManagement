import json
import os
import atexit
from bson import ObjectId
from collections import Counter

from flask import Flask, jsonify
import pymongo

import requests

import pika
import uuid

############ RabbitMQ Start #############
def on_response(ch, method, props, body):
    if correlation_id == props.correlation_id:
        print("Heard Response!" + body)
        response = body

def call(body):
    response = None
    correlation_id = str(uuid.uuid4())
    channel.basic_publish(exchange='', routing_key='rpc_stock_queue', properties=pika.BasicProperties(reply_to=callback_queue, correlation_id=correlation_id,), body=body)
    while response is None:
        connection.process_data_events()
    return response

connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq'))

channel = connection.channel()

result = channel.queue_declare(queue='', exclusive=True)
callback_queue = result.method.queue

channel.basic_consume(queue=callback_queue, on_message_callback=on_response, auto_ack=True)

correlation_id = None
response = None

print("Trying to make a RPC call!", flush=True)
call('{"command": "tst", "args": [123, "string"]}')
############ RabbitMQ End ############


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
    connection.close()
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

    return jsonify({"success": True}), 200


@app.post('/addItem/<order_id>/<item_id>')
def add_item(order_id, item_id):
    # POST - adds a given item in the order given
    if orders.update_one(
        {"_id" : ObjectId(order_id)},
        {"$push" : {"items" : item_id}}
    ).modified_count != 1:
        return jsonify({'error' : f"Could not add {item_id} to order {order_id}"}), 400

    return jsonify({"success": True}), 200


@app.delete('/removeItem/<order_id>/<item_id>')
def remove_item(order_id, item_id):
    # DELETE - removes the given item from the given order
    if orders.update_one(
        {"_id" : ObjectId(order_id)},
        {"$pull" : {"items" : item_id}}
    ).modified_count != 1:
        return jsonify({'error' : f"Could not remove {item_id} to order {order_id}"}), 400

    return jsonify({"success": True}), 200



@app.get('/find/<order_id>')
def find_order(order_id):
    # TODO
    # GET - retrieves the information of an order (id, payment status, items included and user id)
    # Output JSON fields:
        # “order_id”  - the order’s id
        # “paid” (true/false)
        # “items”  - list of item ids that are included in the order
        # “user_id”  - the user’s id that made the order
        # “total_cost” - the total cost of the items in the order
    order = orders.find_one({"_id": ObjectId(order_id)})
    order_items = order["items"]

    total_cost = 0 # TODO this could def be made better
    for order_item in order_items:
        order_item_response = requests.get(f"{gateway_url}/stock/find/{order_item}")
        
        if order_item_response.status_code >= 400:
            return jsonify({"error" : f"could not find item to calculate total cost!"}), 400
        
        total_cost += float(order_item_response.json()["price"])

    payment_resp = requests.post(f"{gateway_url}/payment/status/{order['user_id']}/{order['_id']}")
    
    if payment_resp.status_code >= 400:
        return jsonify({"error" : f"could not find payment status!"}), 400

    return {
        'order_id' : str(order['_id']),
        'paid' : payment_resp.json()['paid'],
        'items' : order['items'],
        'user_id' : str(order['user_id']),
        'total_cost' : total_cost
    }


@app.post('/checkout/<order_id>')
def checkout(order_id):
    # TODO WIP (currently succeeds when it shouldn't. also does not undo any changes)

    # POST - makes the payment (via calling the payment service),
    # subtracts the stock (via the stock service)
    # and returns a status (success/failure).

    order = find_order(order_id)

    payment_resp = make_payment(order)
    if(payment_resp[1] >= 400):
        #Payment fail
        return jsonify({"error" : f"could not pay"}), 400

    order_items = order["items"]
    
    order_items_counts = Counter(order_items)
    
    completed_items = []

    for order_item, count in order_items_counts.most_common(): 
        resp = requests.post(f"{gateway_url}/stock/subtract/{order_item}/{count}")
        if (resp.status_code >= 400):
            ## Attempt to undo what has happened so far. Stock subtraction failed.
            refund_resp = undo_payment(order)
            stock_resp = undo_stock_update(completed_items)
            if refund_resp[1] >= 400 or stock_resp[1] >= 400:
                return jsonify({"error" : f"could not undo. Refund Status Code: {refund_resp[1]}, StockUndo Status Code: {stock_resp[1]}"}), 400
            return jsonify({"error": f"check out failed due to insufficient funds or stock. successfully reverted"}), 444
        else:
            completed_items.append((order_item, count))

    return jsonify({"success": True}), 200

def make_payment(order):
    resp = requests.post(f"{gateway_url}/payment/pay/{order['user_id']}/{order['order_id']}/{order['total_cost']}")
    if (resp.status_code >= 400):
        return jsonify({"error" : f"could not pay"}), resp.status_code
    else:
        return jsonify({"success" : True}), 200

def undo_payment(order):
    resp = requests.post(f"{gateway_url}/payment/add_funds/{order['user_id']}/{order['total_cost']}")
    if (resp.status_code >= 400):
        return jsonify({"error" : f"could not refund"}), resp.status_code
    else:
        return jsonify({"success" : True}), 200

def undo_stock_update(completed_items):
    for completed_item, count in completed_items:
        resp = requests.post(f"{gateway_url}/stock/add/{completed_item}/{count}")
        if (resp.status_code >= 400):
            return jsonify({"error" : f"could not subtract stock and Failed to rollback previous stock updates."}), 400
    return jsonify({"success" : True}), 200