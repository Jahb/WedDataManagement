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


class PaymentQueueDispatcher(object):
    connection: AbstractConnection
    channel: AbstractChannel
    callback_queue: AbstractQueue
    loop: asyncio.AbstractEventLoop

    def __init__(self) -> None:
        self.futures: MutableMapping[str, asyncio.Future] = {}
        self.loop = asyncio.get_running_loop()

    async def connect(self) -> "PaymentQueueDispatcher":
        self.connection = await connect(
            "amqp://admin:admin@mq/", loop=self.loop,
        )
        self.channel = await self.connection.channel()
        self.callback_queue = await self.channel.declare_queue(exclusive=True)
        await self.callback_queue.consume(self.on_response)

        return self


    def on_response(self, message: AbstractIncomingMessage) -> None:
        if message.correlation_id is None:
            print(f"Bad message {message!r}")
            return

        future: asyncio.Future = self.futures.pop(message.correlation_id)
        future.set_result(message.body)
    
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
            routing_key="payment-queue",
        )

        resp = await future
        result = json.loads(resp.decode())
        if 'error' in result:
            LOGGER.exception(operation + " error %r", result['error'])
            raise result['error']
        return result

    async def send_create_user(self):
        return await self.send(operation='create_user')

    async def send_find_user(self, user_id):
        return await self.send(operation='find_user', user_id=user_id)

    async def send_add_credit(self, user_id, amount):
        return await self.send(operation='add_credit', user_id=user_id, amount=amount)

    async def send_remove_credit(self, user_id, order_id, amount):
        return await self.send(operation='remove_credit', user_id=user_id, order_id=order_id, amount=amount)

    async def send_cancel_payment(self, user_id, order_id):
        return await self.send(operation='cancel_payment', user_id=user_id, order_id=order_id)

    async def send_payment_status(self, user_id, order_id):
        return await self.send(operation='payment_status', user_id=user_id, order_id=order_id)
