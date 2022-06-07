from http import HTTPStatus
import os
import atexit
from bson import ObjectId
from collections import Counter

from fastapi import FastAPI, HTTPException
import pymongo

from queue_dispatcher import QueueDispatcher

from time import sleep
import logging
import asyncio

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

rpc: QueueDispatcher


app = FastAPI(title="order-service")

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


@app.on_event('startup')
async def startup():
    sleep(10)
    global rpc
    rpc = await QueueDispatcher().connect()

gateway_url = os.environ["GATEWAY_URL"]

atexit.register(close_db_connection)


@app.post('/create/{user_id}')
def create_order(user_id):
    # POST - creates an order for the given user, and returns an order_id
    # Output JSON fields: “order_id”  - the order’s id
    order = {"user_id": user_id}
    orders.insert_one(order)

    return {
        "order_id": str(order['_id'])
    }


@app.delete('/remove/{order_id}')
def remove_order(order_id):
    # DELETE - deletes an order by ID
    if orders.delete_one({"_id": ObjectId(order_id)}).modified_count != 1:
        raise HTTPException(400, f"Could not delete order {order_id}")

    return {"success": True}


@app.post('/addItem/{order_id}/{item_id}')
def add_item(order_id, item_id):
    # POST - adds a given item in the order given
    if orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$push": {"items": item_id}}
    ).modified_count != 1:
        raise HTTPException(
            400, f"Could not add {item_id} to order {order_id}")

    return {"success": True}


@app.delete('/removeItem/{order_id}/{item_id}')
def remove_item(order_id, item_id):
    # DELETE - removes the given item from the given order
    if orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$pull": {"items": item_id}}
    ).modified_count != 1:
        raise HTTPException(
            400, f"Could not remove {item_id} to order {order_id}")

    return {"success": True}


@app.get('/find/{order_id}')
async def find_order(order_id):
    # GET - retrieves the information of an order (id, payment status, items included and user id)
    # Output JSON fields:
    # “order_id”  - the order’s id
    # “paid” (true/false)
    # “items”  - list of item ids that are included in the order
    # “user_id”  - the user’s id that made the order
    # “total_cost” - the total cost of the items in the order
    order = orders.find_one({"_id": ObjectId(order_id)})
    order_items = order["items"]

    counted_items = dict(Counter(order_items))
    cost_response = await rpc.send_get_total_cost(counted_items)
    if 'error' in cost_response:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY,
                            f"could not find item info: {cost_response['error']}")

    total_cost = float(cost_response['total_cost'])

    payment_resp = await rpc.send_payment_status(
        str(order['user_id']), str(order['_id']))
    if 'error' in payment_resp:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY,
                            f"could not find payment status: {payment_resp['error']}")

    return {
        'order_id': str(order['_id']),
        'paid': payment_resp['paid'],
        'items': order['items'],
        'user_id': str(order['user_id']),
        'total_cost': total_cost
    }


@app.post('/checkout/{order_id}')
async def checkout(order_id):
    # POST - makes the payment (via calling the payment service),
    # subtracts the stock (via the stock service)
    # and returns a status (success/failure).

    order = await find_order(order_id)
    user_id = str(order['user_id'])
    total_cost = float(order['total_cost'])

    payment_resp = await rpc.send_remove_credit(user_id, order_id, total_cost)
    if 'error' in payment_resp:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY,
                            f"could not make payment attempt {payment_resp['error']}")
    if not payment_resp['done']:
        raise HTTPException(HTTPStatus.PRECONDITION_FAILED,
                            "insufficient funds for payment")

    async def refund():
        refund_resp = await rpc.send_cancel_payment(user_id, order_id)
        if 'error' in refund_resp or not refund_resp['done']:
            LOGGER.exception("refund failed! %r", refund_resp.get('error'))
            raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, "refund failed!")

    order_items_counts = dict(Counter(order["items"]))
    stock_resp = await rpc.send_remove_multiple_stocks(order_items_counts, order_id)
    if 'error' in stock_resp:
        await refund()
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY,
                            f"could not deduct stocks because of error {stock_resp['error']}")
    if not stock_resp['done']:
        await refund()
        raise HTTPException(HTTPStatus.PRECONDITION_FAILED,
                            "could not deduct stocks because of insufficient quantities")
    return {"done": True}
