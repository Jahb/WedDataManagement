#!/usr/bin/env python
from flask import jsonify
import pika
import uuid
import json
import logging

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

class PaymentQueueDispatcher(object):

    def __init__(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host='mq', 
                credentials=pika.PlainCredentials('admin', 'admin'),
                heartbeat=600))

        self.channel = self.connection.channel()

        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue

        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True)

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            LOGGER.info(props)
            LOGGER.info(method)

            self.response = body

    def call(self, n):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(
            exchange='',
            routing_key='rpc_queue',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=str(n))
        while self.response is None:
            self.connection.process_data_events()
        return int(self.response)

    def send_remove_credit(self, user_id, order_id, amount):
        self.response = None
        self.corr_id = str(order_id)
        self.channel.basic_publish(
            exchange='',
            routing_key='remove_credit',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=json.dumps({
                'user_id' : user_id, 
                'order_id' : order_id, 
                'amount' : amount})
        )
        while self.response is None:
            self.connection.process_data_events()
        resp = json.loads(self.response)
        if (resp['success']):
            return resp
        else:
            raise Exception(resp['error'])
