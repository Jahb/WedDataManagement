from http import HTTPStatus
import os
import atexit

import json

from fastapi import FastAPI, HTTPException
from typing import Any

import pymongo
from bson.objectid import ObjectId

import logging
from time import sleep
import threading
import asyncio

from aio_pika import Message, connect
from aio_pika.abc import AbstractIncomingMessage

from payment_queue_dispatcher import PaymentQueueDispatcher

class UnknownException(Exception):
    pass


LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

rpc: PaymentQueueDispatcher

app = FastAPI(title="payment-service")

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


@app.on_event('startup')
async def startup():
    sleep(10)
    global rpc
    rpc = await PaymentQueueDispatcher().connect()
    asyncio.create_task(payment_queue_handler())


@app.post('/create_user')
async def create_user():
    # POST - creates a user with 0 credit
    # Output JSON fields: “user_id” - the user’s id
    resp = await rpc.send_create_user()
    if 'error' in resp:
        LOGGER.exception(f"create_user error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    return resp


@app.get('/find_user/{user_id}')
async def find_user(user_id: str):
    # GET - returns the user information
    # Output JSON fields:
    #   “user_id” - the user’s id
    #   “credit” - the user’s credit
    resp = await rpc.send_find_user(user_id)
    if 'error' in resp:
        LOGGER.exception(f"find_user error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    return resp


@app.post('/add_funds/{user_id}/{amount}')
async def add_credit(user_id: str, amount: float):
    # POST - adds funds (amount) to the user’s (user_id) account
    # Output JSON fields: “done” (true/false)
    resp = await rpc.send_add_credit(user_id, amount)
    if 'error' in resp:
        LOGGER.exception(f"add_credit error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    if not resp['done']:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, "add_credit did not complete")
    return resp



@app.post('/pay/{user_id}/{order_id}/{amount}')
async def remove_credit(user_id: str, order_id: str, amount: float):
    # POST - subtracts the amount of the order from the user’s credit (returns failure if credit is not enough)
    resp = await rpc.send_remove_credit(user_id, order_id, amount)
    if 'error' in resp:
        LOGGER.exception(f"remove_credit error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    if not resp['done']:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, "remove_credit did not complete")
    return resp


@app.post('/cancel/{user_id}/{order_id}')
async def cancel_payment(user_id: str, order_id: str):
    resp = await rpc.send_cancel_payment(user_id, order_id)
    if 'error' in resp:
        LOGGER.exception(f"cancel_payment error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    if not resp['done']:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, "cancel_payment did not complete")
    return resp


@app.post('/status/{user_id}/{order_id}')
async def payment_status(user_id: str, order_id: str):
    resp = await rpc.send_payment_status(user_id, order_id)
    if 'error' in resp:
        LOGGER.exception(f"payment_status error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    return resp


# the implementations will only throw if something goes unexpectedly wrong

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


def add_credit_impl(user_id: str, amount: float) -> dict:
    return {'done': users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": float(amount)}}).modified_count == 1}


def remove_credit_impl(user_id, order_id, amount) -> dict:
    with client.start_session() as session:
        with session.start_transaction():
            try:
                available_credit = float(users.find_one(
                    {"_id":  ObjectId(user_id)})["credit"])

                if available_credit < float(amount):
                    return {'done': False}

                payment_barrier.insert_one(
                    {"_id": ObjectId(order_id), "amount": float(amount)})
                if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": -float(amount)}}).modified_count == 1:
                    return {'done': True}

            except pymongo.errors.DuplicateKeyError as e:
                return {'done': True}
        
    raise UnknownException()


def cancel_payment_impl(user_id: str, order_id: str) -> dict:
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
                    return {'done': True}

                amount = float(barrier_entry["amount"])

                cancel_payment_barrier.insert_one({"_id": ObjectId(order_id)})
                if users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"credit": amount}}).modified_count == 1:
                    return {'done': True}
            except pymongo.errors.DuplicateKeyError as e:
                return {'done' : True}

    raise UnknownException()


def payment_status_impl(order_id: str) -> dict:
    # GET - returns the status of the payment (paid or not)
    # Output JSON fields: “paid” (true/false)
    payment_made = payment_barrier.find_one(
        {"_id": ObjectId(order_id)}) is not None
    payment_cancelled = cancel_payment_barrier.find_one(
        {"_id": ObjectId(order_id)}) is not None

    return {'paid': payment_made and not payment_cancelled}


async def payment_queue_handler() -> None:
    # should only throw when receiving an unknown operation
    # which should never happen unless we messed up. so throwing is probably fine
    connection = await connect("amqp://admin:admin@mq/")

    channel = await connection.channel()
    exchange = channel.default_exchange

    queue = await channel.declare_queue('payment-queue')

    LOGGER.info("[payment-queue] connected to queue")

    async with queue.iterator() as qiterator:
        message: AbstractIncomingMessage
        async for message in qiterator:
            try:
                async with message.process(requeue=False):
                    assert message.reply_to is not None
                
                    req = json.loads(message.body.decode())

                    operation = req['operation']

                    arg_info_str = ', '.join(map(lambda s: str(s), filter(
                        None, (req.get('user_id'), req.get('order_id'), req.get('amount')))))
                    LOGGER.info(
                        f"[payment-queue] received message {operation}({arg_info_str}) [{req}]")

                    resp: dict = None

                    if operation == 'create_user':
                        resp = create_user_impl()
                    elif operation == 'find_user':
                        resp = find_user_impl(req['user_id'])
                    elif operation == 'add_credit':
                        resp = add_credit_impl(req['user_id'], req['amount'])
                    elif operation == 'remove_credit':
                        resp = remove_credit_impl(req['user_id'], req['order_id'], req['amount'])
                    elif operation == 'cancel_payment':
                        resp = cancel_payment_impl(req['user_id'], req['order_id'])
                    elif operation == 'payment_status':
                        resp = payment_status_impl(req['order_id'])
                    else:
                        raise Exception(f"Unknown operation {operation}")
                    await exchange.publish(
                        Message(body=json.dumps(resp).encode(), correlation_id=message.correlation_id),
                        routing_key=message.reply_to)
                    LOGGER.info(f"[payment-queue] completed message {operation}({arg_info_str})")
            except Exception as e:
                LOGGER.exception("[payment-queue] processing error %r for message %r", e, message)
                await exchange.publish(
                    Message(body=json.dumps({'error': repr(e)}).encode(), correlation_id=message.correlation_id),
                    routing_key=message.reply_to)
