import os
import atexit

from flask import Flask

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

@app.post('/create_user')
def create_user():
    # POST - creates a user with 0 credit
    # Output JSON fields: “user_id” - the user’s id
    user = { "credit" : 0 }
    users.insert_one(user)
    user["_id"] = str(user["_id"])
    # user["user_id"] = str(user["_id"])
    return user


@app.get('/find_user/<user_id>')
def find_user(user_id: str):
    # GET - returns the user information
    # Output JSON fields:
    #   “user_id” - the user’s id
    #   “credit” - the user’s credit
    user = users.find_one({ "_id" :  ObjectId(user_id) })
    return {
        "user_id" : user_id,
        "credit" : int(user["credit"])
    }


@app.post('/add_funds/<user_id>/<amount>')
def add_credit(user_id: str, amount: int):
    # POST - adds funds (amount) to the user’s (user_id) account
    # Output JSON fields: “done” (true/false)
    if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"stock" : amount}}).modified_count == 1:
        return jsonify(success=True)
    else:
        return jsonify({'error': 'Fail'}), 400



@app.post('/pay/<user_id>/<order_id>/<amount>')
def remove_credit(user_id: str, order_id: str, amount: int):
    # POST - subtracts the amount of the order from the user’s credit (returns failure if credit is not enough)
    with client.start_session() as session:
        with session.start_transaction():
            available_credit = int(users.find_one({ "_id" :  ObjectId(user_id) })["credit"])

            if available_credit < amount:
                return jsonify({'error': f"User {user_id} has only {available_credit} but {amount} is required"}), 400

            payment_barrier.insert_one({"_id" : ObjectId(order_id), "amount" : amount})
            if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"stock" : -amount}}).modified_count == 1:
                return jsonify(success=True)
    return jsonify({'error': 'Fail'}), 400


@app.post('/cancel/<user_id>/<order_id>')
def cancel_payment(user_id: str, order_id: str):
    with client.start_session() as session:
        with session.start_transaction():
            barrier_entry = payment_barrier.find_one({"_id" : ObjectId(order_id)})
            if barrier_entry is None:
                return jsonify(success=True) # TODO: is this correct? the original payment did not go through, so after cancelling we are in a good state

            amount = int(barrier_entry["amount"])

            cancel_payment_barrier.insert_one({"_id" : ObjectId(order_id)})
            if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"stock" : amount}}).modified_count == 1:
                return jsonify(success=True)
    return jsonify({'error': 'Fail'}), 400


@app.post('/status/<user_id>/<order_id>')
def payment_status(user_id: str, order_id: str):
    # GET - returns the status of the payment (paid or not)
    # Output JSON fields: “paid” (true/false)

    payment_made = payment_barrier.find_one({"_id" : ObjectId(order_id)}) is not None
    payment_cancelled = cancel_payment_barrier.find_one({"_id" : ObjectId(order_id)}) is not None

    return {"paid" : payment_made and not payment_cancelled}
