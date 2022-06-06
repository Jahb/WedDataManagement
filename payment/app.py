import os
import atexit

import json

from flask import Flask, jsonify
from typing import Any

import pymongo
from bson.objectid import ObjectId

import logging
from time import sleep
import pika
import threading

from payment_queue_dispatcher import PaymentQueueDispatcher


class InsufficientFundException(Exception):
    pass


class DuplicateOperationException(Exception):
    pass


class UnknownException(Exception):
    pass


LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

sleep(10)
rpc = PaymentQueueDispatcher()

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
    try:
        resp = rpc.send_create_user()
        return jsonify({'user_id': resp['user_id']})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.get('/find_user/<user_id>')
def find_user(user_id: str):
    # GET - returns the user information
    # Output JSON fields:
    #   “user_id” - the user’s id
    #   “credit” - the user’s credit
    try:
        resp = rpc.send_find_user(user_id)
        return jsonify({'user_id': user_id, 'credit': resp['credit']})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.post('/add_funds/<user_id>/<amount>')
def add_credit(user_id: str, amount: float):
    # POST - adds funds (amount) to the user’s (user_id) account
    # Output JSON fields: “done” (true/false)
    try:
        rpc.send_add_credit(user_id, amount)
        return jsonify({"done": True}), 200
    except Exception as e:
        return jsonify({'error': f"User {user_id} could not be updated"}), 400


@app.post('/pay/<user_id>/<order_id>/<amount>')
def remove_credit(user_id: str, order_id: str, amount: float):
    # POST - subtracts the amount of the order from the user’s credit (returns failure if credit is not enough)
    try:
        rpc.send_remove_credit(user_id, order_id, amount)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.post('/cancel/<user_id>/<order_id>')
def cancel_payment(user_id: str, order_id: str):
    try:
        rpc.send_cancel_payment(user_id, order_id)
        return jsonify(success=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.post('/status/<user_id>/<order_id>')
def payment_status(user_id: str, order_id: str):
    try:
        resp = rpc.send_payment_status(user_id, order_id)
        return jsonify({"paid": resp['paid']}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400


def create_user_impl() -> dict:
    user = {"credit": 0}
    users.insert_one(user)
    return {
        "user_id": str(user['_id'])
    }


def find_user_impl(user_id: str) -> dict:
    user = users.find_one({"_id":  ObjectId(user_id)})
    return {
        "user_id": user_id,
        "credit": float(user["credit"])
    }


def add_credit_impl(user_id: str, amount: float) -> bool:
    return users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": float(amount)}}).modified_count == 1


def remove_credit_impl(user_id, order_id, amount) -> None:
    with client.start_session() as session:
        with session.start_transaction():
            try:
                available_credit = float(users.find_one(
                    {"_id":  ObjectId(user_id)})["credit"])

                if available_credit < float(amount):
                    raise InsufficientFundException(
                        f"User {user_id} has only {available_credit} but {amount} is required")

                payment_barrier.insert_one(
                    {"_id": ObjectId(order_id), "amount": float(amount)})
                if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": -float(amount)}}).modified_count == 1:
                    return
                else:
                    raise UnknownException()

            except pymongo.errors.DuplicateKeyError as e:
                raise DuplicateOperationException(e)


def cancel_payment_impl(user_id: str, order_id: str) -> None:
    with client.start_session() as session:
        with session.start_transaction():
            try:
                barrier_entry = payment_barrier.find_one(
                    {"_id": ObjectId(order_id)})
                if barrier_entry is None:
                    # insert ID into idempotency barriers so that we do not attempt to cancel payment again
                    # or retry payment
                    payment_barrier.insert_one(
                        {"_id": ObjectId(order_id), "amount": float(amount)})
                    cancel_payment_barrier.insert_one(
                        {"_id": ObjectId(order_id)})
                    return

                amount = float(barrier_entry["amount"])

                cancel_payment_barrier.insert_one({"_id": ObjectId(order_id)})
                if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": amount}}).modified_count == 1:
                    return
            except pymongo.errors.DuplicateKeyError as e:
                raise DuplicateOperationException(e)

    raise UnknownException()


def payment_status_impl(order_id: str) -> bool:

    # GET - returns the status of the payment (paid or not)
    # Output JSON fields: “paid” (true/false)

    payment_made = payment_barrier.find_one(
        {"_id": ObjectId(order_id)}) is not None
    payment_cancelled = cancel_payment_barrier.find_one(
        {"_id": ObjectId(order_id)}) is not None

    return payment_made and not payment_cancelled


def payment_queue_handler() -> None:
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host='mq',
            credentials=pika.PlainCredentials('admin', 'admin'),
            heartbeat=600))

    channel = connection.channel()
    channel.queue_declare(queue='payment-queue')

    def _on_request(ch, method, props, *, success: bool = True, duplicate: bool = False, error: Any = None, body: dict = {}):
        ch.basic_publish(exchange='',
                         routing_key=props.reply_to,
                         properties=pika.BasicProperties(
                             correlation_id=props.correlation_id),
                         body=json.dumps(body | {"success": success, "duplicate": duplicate, "error": str(error)}))

    def queue_receive_message(ch, method, props, req):
        body = json.loads(req.decode('utf-8'))
        operation = body['operation']

        arg_info_str = ', '.join(map(lambda s: str(s), filter(
            None, (body.get('user_id'), body.get('order_id'), body.get('amount')))))
        LOGGER.info(
            f"[payment-queue] received message {operation}({arg_info_str})")

        try:
            if operation == 'create_user':
                _queue_create_user(ch, method, props)
            elif operation == 'find_user':
                _queue_find_user(ch, method, props, body)
            elif operation == 'add_credit':
                _queue_add_credit(ch, method, props, body)
            elif operation == 'remove_credit':
                _queue_remove_credit(ch, method, props, body)
            elif operation == 'cancel_payment':
                _queue_cancel_payment(ch, method, props, body)
            elif operation == 'payment_status':
                _queue_payment_status(ch, method, props, body)
            else:
                LOGGER.error(f"Unknown operation: {operation}")
                _on_request(ch, method, props, success=False,
                            error=f"Unknown op {operation}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            LOGGER.warn(f"[payment-queue] {operation} raised {e}")
            _on_request(ch, method, props, success=False, error=e)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def _queue_create_user(ch, method, props):
        user = create_user_impl()

        _on_request(ch, method, props, body=user)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def _queue_find_user(ch, method, props, body):
        user_id = str(body['user_id'])

        user = find_user_impl(user_id)

        _on_request(ch, method, props, body=user)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def _queue_add_credit(ch, method, props, body):
        user_id = str(body['user_id'])
        amount = float(body['amount'])

        success = add_credit_impl(user_id, amount)

        _on_request(ch, method, props, success=success)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def _queue_remove_credit(ch, method, props, body):
        user_id = str(body['user_id'])
        order_id = str(body['order_id'])
        amount = float(body['amount'])

        try:
            remove_credit_impl(user_id, order_id, amount)
            LOGGER.info(f"[payment-queue] remove_credit ACK")
            _on_request(ch, method, props)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except DuplicateOperationException as e:
            _on_request(ch, method, props, duplicate=True)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except InsufficientFundException as e:
            LOGGER.info(
                f"[payment-queue] remove_credit could not succeed because of {e}")
            _on_request(ch, method, props, success=False, error=e)
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def _queue_cancel_payment(ch, method, props, body):
        user_id = str(body['user_id'])
        order_id = str(body['order_id'])

        try:
            cancel_payment_impl(user_id, order_id)
            _on_request(ch, method, props)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except DuplicateOperationException as e:
            _on_request(ch, method, props, duplicate=True)
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def _queue_payment_status(ch, method, props, body):
        # user_id = str(body['user_id'])
        order_id = str(body['order_id'])

        result = payment_status_impl(order_id)

        _on_request(ch, method, props, body={'paid': result})
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='payment-queue',
                          on_message_callback=queue_receive_message)

    print(" [x] Awaiting RPC requests")
    channel.start_consuming()


# start a seperate thread to check queue
t = threading.Thread(target=payment_queue_handler, args=())
t.start()
