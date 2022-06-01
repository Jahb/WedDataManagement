import os
import atexit

from flask import Flask, jsonify
from typing import List, Tuple

import datetime
from time import sleep

from kubemq.commandquery import ChannelParameters, Channel, RequestType, Request, Responder
from kubemq.commandquery.response import Response
from kubemq.subscription import SubscribeType, EventsStoreType, SubscribeRequest
from kubemq.tools import ListenerCancellationToken

PAYMENT_CHANNEL = "payments"
CLIENT_ID = "payment-app-1"

import pymongo
from bson.objectid import ObjectId


app = Flask("payment-service")

client: pymongo.MongoClient = pymongo.MongoClient(
    host=os.environ['MONGO_HOST'],
    port=int(os.environ['MONGO_PORT']),
    username=os.environ['MONGO_USERNAME'],
    password=os.environ['MONGO_PASSWORD'],
)

db = client["webDataManagement"]

users = db["users"]
payment_barrier = db["payment_barrier"]
cancel_payment_barrier = db["cancel_payment_barrier"]


def close_db_connection():
    client.close()


atexit.register(close_db_connection)

cancel_token = ListenerCancellationToken()

def handle_incoming_request(request):
    if request:
        print("Subscriber Received request: Metadata:'%s', Channel:'%s', Body:'%s' tags:%s" % (
            request.metadata,
            request.channel,
            request.body,
            request.tags
        ))
        response = Response(request)
        response.body = "OK".encode('UTF-8')
        response.cache_hit = False
        response.error = "None"
        response.client_id = CLIENT_ID
        response.executed = True
        response.metadata = "OK"
        response.timestamp = datetime.datetime.now()
        return response


def handle_incoming_error(error_msg):
    print("received error:%s'" % (
        error_msg
    ))

try:
    responder = Responder("9090:9090")
    subscribe_request = SubscribeRequest(
        channel=PAYMENT_CHANNEL,
        client_id=CLIENT_ID,
        events_store_type=EventsStoreType.Undefined,
        events_store_type_value=0,
        group="",
        subscribe_type=SubscribeType.Commands
    )
    responder.subscribe_to_requests(subscribe_request, handle_incoming_request, handle_incoming_error, cancel_token)
except Exception as err:
    print(f'error, error: {err}')

@app.post('/create_user')
def create_user():
    # POST - creates a user with 0 credit
    # Output JSON fields: “user_id” - the user’s id
    user = {"credit": 0}
    users.insert_one(user)
    return jsonify({
        "user_id": str(user['_id'])
    })


@app.get('/find_user/<user_id>')
def find_user(user_id: str):
    # GET - returns the user information
    # Output JSON fields:
    #   “user_id” - the user’s id
    #   “credit” - the user’s credit
    user = users.find_one({"_id":  ObjectId(user_id)})
    return jsonify({
        "user_id": user_id,
        "credit": float(user["credit"])
    })


@app.post('/add_funds/<user_id>/<amount>')
def add_credit(user_id: str, amount: float):
    # POST - adds funds (amount) to the user’s (user_id) account
    # Output JSON fields: “done” (true/false)
    if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": float(amount)}}).modified_count != 1:
        return jsonify({'error': f"User {user_id} could not be updated"}), 400

    return jsonify({"done": True}), 200


@app.post('/pay/<user_id>/<order_id>/<amount>')
def remove_credit(user_id: str, order_id: str, amount: float):
    # POST - subtracts the amount of the order from the user’s credit (returns failure if credit is not enough)
    with client.start_session() as session:
        with session.start_transaction():
            try: 
                available_credit = float(users.find_one({"_id":  ObjectId(user_id)})["credit"])

                if available_credit < float(amount):
                    return jsonify({'error': f"User {user_id} has only {available_credit} but {amount} is required"}), 400

                payment_barrier.insert_one({"_id": ObjectId(order_id), "amount": float(amount)})
                if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": -float(amount)}}).modified_count == 1:
                    return jsonify(success=True)
            except pymongo.errors.DuplicateKeyError as e: 
                return jsonify({"success": True, "duplicate_error": str(e)}), 222
            except Exception as e:
                return jsonify({"error": str(e)}), 400

    return jsonify({'error': 'Fail'}), 400


@app.post('/cancel/<user_id>/<order_id>')
def cancel_payment(user_id: str, order_id: str):
    with client.start_session() as session:
        with session.start_transaction():
            try:
                barrier_entry = payment_barrier.find_one({"_id": ObjectId(order_id)})
                if barrier_entry is None:         
                    # insert ID into idempotency barriers so that we do not attempt to cancel payment again
                    # or retry payment       
                    payment_barrier.insert_one({"_id": ObjectId(order_id), "amount": float(amount)})                
                    cancel_payment_barrier.insert_one({"_id": ObjectId(order_id)})
                    return jsonify(success=True)

                amount = float(barrier_entry["amount"])

                cancel_payment_barrier.insert_one({"_id": ObjectId(order_id)})
                if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": amount}}).modified_count == 1:
                    return jsonify(success=True)
            except pymongo.errors.DuplicateKeyError as e: 
                return jsonify({"success": True, "duplicate_error": str(e)}), 222
            except Exception as e:
                return jsonify({"error": str(e)}), 400
    return jsonify({'error': 'Fail'}), 400


@app.post('/status/<user_id>/<order_id>')
def payment_status(user_id: str, order_id: str):
    # GET - returns the status of the payment (paid or not)
    # Output JSON fields: “paid” (true/false)

    payment_made = payment_barrier.find_one({"_id": ObjectId(order_id)}) is not None
    payment_cancelled = cancel_payment_barrier.find_one({"_id": ObjectId(order_id)}) is not None

    return jsonify({"paid": payment_made and not payment_cancelled}), 200
