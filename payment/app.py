from concurrent.futures import thread
import os
import atexit
from urllib import response

import json

from flask import Flask, jsonify
from typing import Any, List, Tuple

import pymongo
from bson.objectid import ObjectId

import functools
import logging
from time import sleep
import pika
from pika.exchange_type import ExchangeType
import threading

class InsufficientFundException(Exception):
    pass
class DuplicateOperationException(Exception):
    pass
class UnknownException(Exception):
    pass


LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

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

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

def close_db_connection():
    client.close()


atexit.register(close_db_connection)

@app.post('/create_user')
def create_user():
    # POST - creates a user with 0 credit
    # Output JSON fields: “user_id” - the user’s id
    return jsonify(create_user_impl())

def create_user_impl():
    user = {"credit": 0}
    users.insert_one(user)
    return {
        "user_id": str(user['_id'])
    }


@app.get('/find_user/<user_id>')
def find_user(user_id: str):
    # GET - returns the user information
    # Output JSON fields:
    #   “user_id” - the user’s id
    #   “credit” - the user’s credit
    return jsonify(find_user_impl(user_id))

def find_user_impl(user_id: str):
    user = users.find_one({"_id":  ObjectId(user_id)})
    return {
        "user_id": user_id,
        "credit": float(user["credit"])
    }

@app.post('/add_funds/<user_id>/<amount>')
def add_credit(user_id: str, amount: float):
    # POST - adds funds (amount) to the user’s (user_id) account
    # Output JSON fields: “done” (true/false)
    if not add_credit_impl(user_id, amount):
        return jsonify({'error': f"User {user_id} could not be updated"}), 400

    return jsonify({"done": True}), 200

def add_credit_impl(user_id: str, amount: float):
    return users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": float(amount)}}).modified_count == 1


@app.post('/pay/<user_id>/<order_id>/<amount>')
def remove_credit(user_id: str, order_id: str, amount: float):
    # POST - subtracts the amount of the order from the user’s credit (returns failure if credit is not enough)
    try:
        remove_credit_impl(user_id, order_id, amount)
        return jsonify({'success' : True}), 200
    except DuplicateOperationException as e:
        return jsonify({"success" : True, "duplicate_error" : str(e)}), 222
    except Exception as e:
        return jsonify({'error' : e}), 400

def remove_credit_impl(user_id, order_id, amount):    
    LOGGER.info(f"attempting to remove {amount}")
    with client.start_session() as session:
        with session.start_transaction():
            try: 
                available_credit = float(users.find_one({"_id":  ObjectId(user_id)})["credit"])

                if available_credit < float(amount):
                    raise InsufficientFundException(f"User {user_id} has only {available_credit} but {amount} is required")

                payment_barrier.insert_one({"_id": ObjectId(order_id), "amount": float(amount)})
                if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": -float(amount)}}).modified_count == 1:
                    return
            except pymongo.errors.DuplicateKeyError as e: 
                raise DuplicateOperationException(e)

    raise UnknownException()


@app.post('/cancel/<user_id>/<order_id>')
def cancel_payment(user_id: str, order_id: str):
    try:
        cancel_payment_impl(user_id, order_id)
        return jsonify(success=True)
    except DuplicateOperationException as e:
        return jsonify({"success": True, "duplicate_error": str(e)}), 222
    except Exception as e:
        return jsonify({'error': str(e)}), 400

def cancel_payment_impl(user_id: str, order_id: str):
    with client.start_session() as session:
        with session.start_transaction():
            try:
                barrier_entry = payment_barrier.find_one({"_id": ObjectId(order_id)})
                if barrier_entry is None:         
                    # insert ID into idempotency barriers so that we do not attempt to cancel payment again
                    # or retry payment       
                    payment_barrier.insert_one({"_id": ObjectId(order_id), "amount": float(amount)})                
                    cancel_payment_barrier.insert_one({"_id": ObjectId(order_id)})
                    return

                amount = float(barrier_entry["amount"])

                cancel_payment_barrier.insert_one({"_id": ObjectId(order_id)})
                if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": amount}}).modified_count == 1:
                    return
            except pymongo.errors.DuplicateKeyError as e:
                raise DuplicateOperationException(e)

    raise UnknownException()


@app.post('/status/<user_id>/<order_id>')
def payment_status(user_id: str, order_id: str):
    return jsonify({"paid": payment_status_impl(order_id)}), 200

def payment_status_impl(order_id: str):

    # GET - returns the status of the payment (paid or not)
    # Output JSON fields: “paid” (true/false)

    payment_made = payment_barrier.find_one({"_id": ObjectId(order_id)}) is not None
    payment_cancelled = cancel_payment_barrier.find_one({"_id": ObjectId(order_id)}) is not None

    return payment_made and not payment_cancelled


def payment_queue_handler():
    sleep(10)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host='mq', 
            credentials=pika.PlainCredentials('admin', 'admin'),
            heartbeat=600))

    channel = connection.channel()
    channel.queue_declare(queue='create_user')
    channel.queue_declare(queue='find_user')
    channel.queue_declare(queue='add_credit')
    channel.queue_declare(queue='remove_credit')
    channel.queue_declare(queue='cancel_payment')
    channel.queue_declare(queue='payment_status')

    def _on_request(ch, method, props, *, success: bool = True, duplicate: bool = False, error: Any = None, body: dict = {}):
        ch.basic_publish(exchange='',
                        routing_key=props.reply_to,
                        properties=pika.BasicProperties(correlation_id = \
                                                            props.correlation_id),
                        body=json.dumps(body | {"success" : success, "duplicate" : duplicate, "error" : error }))
    
    def queue_create_user(ch, method, props, body):
        LOGGER.info(f"[] received payment queue message: create_user()")

        user = create_user_impl()

        _on_request(ch, method, props, body=user)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    
    def queue_find_user(ch, method, props, body):  
        user_id = str(body.decode("utf-8"))
        LOGGER.info(f"[] received payment queue message: find_user({user_id})")

        user = find_user_impl(user_id)

        _on_request(ch, method, props, body=user)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def queue_add_credit(ch, method, props, body):
        req = json.loads(body.decode("utf-8"))
        user_id = str(req['user_id'])
        amount = float(req['amount'])
        LOGGER.info(f"[] received payment queue message: add_credit({user_id}, {amount})")
        
        success = add_credit_impl(user_id, amount)

        _on_request(ch, method, props, success=success)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def queue_remove_credit(ch, method, props, body):
        LOGGER.warn(f"[] body: {body}, {body.decode('utf-8')}")
        req = json.loads(body.decode("utf-8"))
        user_id = str(req['user_id'])
        order_id = str(req['order_id'])
        amount = float(req['amount'])
        LOGGER.info(f"[] received payment queue message: remove_credit({user_id}, {order_id}, {amount})")
        
        try:
            remove_credit_impl(user_id, order_id, amount)
            LOGGER.info(f"[] remove_credit ACK")
            _on_request(ch, method, props)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except DuplicateOperationException as e:
            LOGGER.info(f"[] remove_credit ACK but duplicate ({e})")
            _on_request(ch, method, props, duplicate=True)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except InsufficientFundException as e:
            LOGGER.info(f"[] remove_credit NACK because of {e}")
            _on_request(ch, method, props, success=False, error=str(e))
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            LOGGER.info(f"[] remove_credit NACK because of {e}")
            _on_request(ch, method, props, success=False, error=str(e))
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


    def queue_cancel_payment(ch, method, props, body):
        LOGGER.warn(f"[] body: {body}, {body.decode('utf-8')}")
        req = json.loads(body.decode("utf-8"))
        user_id = str(req['user_id'])
        order_id = str(req['order_id'])
        LOGGER.info(f"[] received payment queue message: cancel_payment({user_id}, {order_id})")
        
        try:
            cancel_payment_impl(user_id, order_id)
            LOGGER.info(f"[] cancel_payment ACK")
            _on_request(ch, method, props)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except DuplicateOperationException as e:
            LOGGER.info(f"[] cancel_payment ACK but duplicate ({e})")
            _on_request(ch, method, props, duplicate=True)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            LOGGER.info(f"[] cancel_payment NACK because of {e}")
            _on_request(ch, method, props, success=False, error=str(e))
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
    
    def queue_payment_status(ch, method, props, body):
        req = json.loads(body.decode("utf-8"))
        user_id = str(req['user_id'])
        order_id = str(req['order_id'])
        LOGGER.info(f"[] received payment queue message: payment_status({user_id}, {order_id})")
        
        result = payment_status_impl(order_id)
        
        _on_request(ch, method, props, body={'result' : result})
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='create_user', on_message_callback=queue_create_user)
    channel.basic_consume(queue='find_user', on_message_callback=queue_find_user)
    channel.basic_consume(queue='add_credit', on_message_callback=queue_add_credit)
    channel.basic_consume(queue='remove_credit', on_message_callback=queue_remove_credit)
    channel.basic_consume(queue='cancel_payment', on_message_callback=queue_cancel_payment)
    channel.basic_consume(queue='payment_status', on_message_callback=queue_payment_status)

    print(" [x] Awaiting RPC requests")
    channel.start_consuming()


# start a seperate thread to check queue
t = threading.Thread(target=payment_queue_handler,args=())
t.start()
