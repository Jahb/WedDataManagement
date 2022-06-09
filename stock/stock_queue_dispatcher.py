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


class StockQueueDispatcher(object):
    connection: AbstractConnection
    channel: AbstractChannel
    callback_queue: AbstractQueue
    loop: asyncio.AbstractEventLoop

    def __init__(self) -> None:
        self.futures: MutableMapping[str, asyncio.Future] = {}
        self.loop = asyncio.get_running_loop()

    async def connect(self) -> "StockQueueDispatcher":
        self.connection = await connect(
            "amqp://admin:admin@mq-service/", loop=self.loop,
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
    
    async def send(self, *, operation, **kwargs) -> Any:
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
            routing_key="stock-queue",
        )

        message: AbstractIncomingMessage = await future
        # await message.ack()
        return json.loads(message.body.decode())

    async def send_create_item(self, price: float):
        return await self.send(operation='create_item', price=price)

    async def send_find_item(self, item_id):
        return await self.send(operation='find_item', item_id=item_id)

    async def send_add_stock(self, item_id, amount):
        return await self.send(operation='add_stock', item_id=item_id, amount=amount)

    async def send_remove_stock(self, item_id, amount):
        return await self.send(operation='remove_stock', item_id=item_id, amount=amount)

    # TODO: create a send_remove_multiple_stock(self, item_dict, idem_key)
