from http import HTTPStatus
import os
import atexit
from fastapi import FastAPI, HTTPException

import pymongo
from bson.objectid import ObjectId
import logging

from time import sleep
import json
import asyncio

from aio_pika import Message, connect
from aio_pika.abc import AbstractIncomingMessage

from stock_queue_dispatcher import StockQueueDispatcher


class UnknownException(Exception):
    pass


LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

rpc: StockQueueDispatcher

app = FastAPI(title="stock-service")

client: pymongo.MongoClient = pymongo.MongoClient(
    host=os.environ['MONGO_HOST'],
    port=int(os.environ['MONGO_PORT']),
    username=os.environ['MONGO_USERNAME'],
    password=os.environ['MONGO_PASSWORD'],
)

db = client["webDataManagement"]

stock = db["stock"]
barrier = db["stock_barrier"]

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


def close_db_connection():
    client.close()


atexit.register(close_db_connection)


@app.on_event('startup')
async def startup():
    sleep(10)
    global rpc
    rpc = await StockQueueDispatcher().connect()
    asyncio.create_task(stock_queue_handler())


# Create a new Item & return the ID
@app.post('/item/create/{price}')
async def create_item(price: float):
    # POST - adds an item and its price, and returns its ID.
    # Output JSON fields:
    # “item_id” - the item’s id
    resp = await rpc.send_create_item(price)
    if 'error' in resp:
        LOGGER.exception(f"find_item error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    return resp


@app.get('/find/{item_id}')
async def find_item(item_id: str):
    # GET - returns an item’s availability and price.
    # Output JSON fields:
    # “stock” - the item’s stock
    # “price” - the item’s price
    resp = await rpc.send_find_item(item_id)
    if 'error' in resp:
        LOGGER.exception(f"find_item error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    return resp


@app.post('/add/{item_id}/{amount}')
async def add_stock(item_id: str, amount: float):
    # POST - adds the given number of stock items to the item count in the stock
    resp = await rpc.send_add_stock(item_id, amount)
    if 'error' in resp:
        LOGGER.exception(f"add_stock error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    if not resp['done']:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY,
                            "could not add stock")
    return resp


@app.post('/subtract/{item_id}/{amount}')
async def remove_stock(item_id: str, amount: float):
    # POST - subtracts an item from stock by the amount specified.
    resp = await rpc.send_remove_stock(item_id, amount)
    if 'error' in resp:
        LOGGER.exception(f"remove_stock error {resp['error']}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, resp['error'])
    if not resp['done']:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY,
                            "insufficient stock")
    return resp


def create_item_impl(price: float):
    # POST - adds an item and its price, and returns its ID.
    # Output JSON fields:
    # “item_id” - the item’s id
    item = {"stock": 0, "price": price}
    stock.insert_one(item)
    return {
        "item_id": str(item["_id"])
    }


def find_item_impl(item_id: str):
    # GET - returns an item’s availability and price.
    # Output JSON fields:
    # “stock” - the item’s stock
    # “price” - the item’s price
    item = stock.find_one({"_id": ObjectId(item_id)})
    return {
        "item_id": str(item["_id"]),
        "stock": int(item["stock"]),
        "price": float(item["price"])
    }


def add_stock_impl(item_id: str, amount: float):
    # POST - adds the given number of stock items to the item count in the stock
    return {"done": stock.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": float(amount)}}).modified_count == 1}


def remove_stock_impl(item_id: str, amount: float):
    # POST - subtracts an item from stock by the amount specified.
    # TODO - how will we make this idempotent?
    with client.start_session() as session:
        with session.start_transaction():
            item = stock.find_one({"_id": ObjectId(item_id)}, session=session)
            if item["stock"] < float(amount):
                return {"done": False}

            if stock.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": -float(amount)}}, session=session).modified_count == 1:
                return {"done": True}

    raise UnknownException()

def remove_multiple_stocks_impl(item_dict: dict[str, int], idem_key: str):
    LOGGER.info("Removing stocks in one transaction: %r", item_dict)
    with client.start_session() as session:
        with session.start_transaction():
            if barrier.find_one({"_id": ObjectId(idem_key)}, session=session) is not None:
                return {"done": True}

            barrier.insert_one({"_id": ObjectId(idem_key)}, session=session)

            for item_id, count in item_dict.items():
                item = stock.find_one({"_id": ObjectId(item_id)}, session=session)
                if item["stock"] < float(count):
                    LOGGER.info(f"insufficient stock. have {item['stock']}, want {count} for {item_id}")
                    session.abort_transaction()
                    return {'done': False}

                LOGGER.info(f"sufficient stock. have {item['stock']}, want {count} for {item_id}")
                if stock.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": -float(count)}}, session=session).modified_count != 1:
                    session.abort_transaction()
                    raise UnknownException()

    return {'done': True}


def get_total_cost_impl(item_dict: dict[str, int]):
    LOGGER.info("Removing stocks in one transaction: %r", item_dict)
    total_price = sum(float(find_item_impl(item_id)['price']) * count for item_id, count in item_dict.items())

    return {'total_cost': total_price}

async def stock_queue_handler() -> None:
    # should only throw when receiving an unknown operation
    # which should never happen unless we messed up. so throwing is probably fine
    connection = await connect("amqp://admin:admin@mq-service/")

    channel = await connection.channel()
    exchange = channel.default_exchange

    queue = await channel.declare_queue('stock-queue')

    LOGGER.info("[stock-queue] connected to queue")

    async with queue.iterator() as qiterator:
        message: AbstractIncomingMessage
        async for message in qiterator:
            try:
                async with message.process(requeue=False):
                    assert message.reply_to is not None

                    req = json.loads(message.body.decode())

                    operation = req['operation']

                    arg_info_str = ', '.join(map(lambda s: str(s), filter(
                        None, (req.get('item_id'), req.get('price'), req.get('amount')))))
                    LOGGER.info(
                        f"[stock-queue] received message {operation}({arg_info_str}) [{req}]")

                    resp: dict = None

                    if operation == 'create_item':
                        resp = create_item_impl(req['price'])
                    elif operation == 'find_item':
                        resp = find_item_impl(req['item_id'])
                    elif operation == 'add_stock':
                        resp = add_stock_impl(req['item_id'], req['amount'])
                    elif operation == 'remove_stock':
                        resp = remove_stock_impl(req['item_id'], req['amount'])
                    elif operation == 'remove_multiple_stock':
                        resp = remove_multiple_stocks_impl(req['item_dict'], req['idem_key'])
                    elif operation == 'total_cost':
                        resp = get_total_cost_impl(req['item_dict'])
                    else:
                        raise Exception(f"Unknown operation {operation}")
                    await exchange.publish(
                        Message(body=json.dumps(resp).encode(),
                                correlation_id=message.correlation_id),
                        routing_key=message.reply_to)
                    LOGGER.info(
                        f"[stock-queue] completed message {operation}({arg_info_str})")
            except Exception as e:
                LOGGER.exception(
                    "[stock-queue] processing error %r for message %r", e, message)
                await exchange.publish(
                    Message(body=json.dumps({'error': repr(e)}).encode(
                    ), correlation_id=message.correlation_id),
                    routing_key=message.reply_to)
