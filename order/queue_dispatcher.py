#!/usr/bin/env python
import json
import logging
import asyncio
import uuid
from typing import MutableMapping, Any

from aio_pika import Message, connect
from aio_pika.abc import (
    AbstractChannel, AbstractConnection, AbstractIncomingMessage, AbstractQueue
)

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)


class QueueDispatcher(object):
    connection: AbstractConnection
    channel: AbstractChannel
    callback_queue: AbstractQueue
    loop: asyncio.AbstractEventLoop

    def __init__(self) -> None:
        self.futures: MutableMapping[str, asyncio.Future] = {}
        self.loop = asyncio.get_running_loop()

    async def connect(self) -> "QueueDispatcher":
        self.connection = await connect(
            "amqp://admin:admin@mq/", loop=self.loop,
        )
        self.channel = await self.connection.channel()
        self.callback_queue = await self.channel.declare_queue(exclusive=True)
        await self.callback_queue.consume(self.on_response, no_ack=True)

        return self


    def on_response(self, message: AbstractIncomingMessage) -> None:
        if message.correlation_id is None:
            print(f"Bad message {message!r}")
            return

        future: asyncio.Future = self.futures.pop(message.correlation_id)
        future.set_result(message)
    
    async def send(self, queue: str, *, operation, **kwargs) -> Any:
        correlation_id = str(uuid.uuid4())
        future = self.loop.create_future()

        self.futures[correlation_id] = future

        await self.channel.default_exchange.publish(
            Message(
                json.dumps({'operation': operation} | kwargs).encode(),
                content_type="text/plain",
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name,
            ),
            routing_key=queue,
        )

        message: AbstractIncomingMessage = await future
        return json.loads(message.body.decode())

    async def send_create_user(self):
        return await self.send('payment-queue', operation='create_user')

    async def send_find_user(self, user_id):
        return await self.send('payment-queue', operation='find_user', user_id=user_id)

    async def send_add_credit(self, user_id, amount):
        return await self.send('payment-queue', operation='add_credit', user_id=user_id, amount=amount)

    async def send_remove_credit(self, user_id, order_id, amount):
        return await self.send('payment-queue', operation='remove_credit', user_id=user_id, order_id=order_id, amount=amount)

    async def send_cancel_payment(self, user_id, order_id):
        return await self.send('payment-queue', operation='cancel_payment', user_id=user_id, order_id=order_id)

    async def send_payment_status(self, user_id, order_id):
        return await self.send('payment-queue', operation='payment_status', user_id=user_id, order_id=order_id)

    async def send_create_item(self, price: float):
        return await self.send('stock-queue', operation='create_item', price=price)

    async def send_find_item(self, item_id):
        return await self.send('stock-queue', operation='find_item', item_id=item_id)

    async def send_add_stock(self, item_id, amount):
        return await self.send('stock-queue', operation='add_stock', item_id=item_id, amount=amount)

    async def send_remove_stock(self, item_id, amount):
        return await self.send('stock-queue', operation='remove_stock', item_id=item_id, amount=amount)

    async def send_remove_multiple_stocks(self, item_dict, idem_key):
        return await self.send('stock-queue', operation='remove_multiple_stock', item_dict=item_dict, idem_key=idem_key)

    async def send_get_total_cost(self, item_dict):
        return await self.send('stock-queue', operation='total_cost', item_dict=item_dict)

    # TODO: create a "send_sum_item_cost(self, item_list)"
