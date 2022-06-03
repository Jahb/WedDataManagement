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

    def send_to_queue(self, corr_id, routing_key, body):
        self.response = None
        self.corr_id = str(corr_id)
        self.channel.basic_publish(
            exchange='',
            routing_key=routing_key,
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=body)
        while self.response is None:
            self.connection.process_data_events()
        resp = json.loads(self.response)
        if (resp['success']):
            return resp
        else:
            raise Exception(resp['error'])

    def send_create_user(self):
        return self.send_to_queue(str(uuid.uuid4()), 'payment-queue', json.dumps({
                'operation' : 'create_user'}))

    def send_find_user(self, user_id):
        return self.send_to_queue(str(uuid.uuid4()), 'payment-queue', json.dumps({
                'operation' : 'find_user',
                'user_id' : user_id}))

    def send_add_credit(self, user_id, amount):
        return self.send_to_queue(str(uuid.uuid4()), 'payment-queue', json.dumps({
                'operation' : 'add_credit',
                'user_id' : user_id,
                'amount' : amount}))

    def send_remove_credit(self, user_id, order_id, amount):
        return self.send_to_queue(str(order_id), 'payment-queue', json.dumps({
                'operation' : 'remove_credit',
                'user_id' : user_id, 
                'order_id' : order_id, 
                'amount' : amount}))

    def send_cancel_payment(self, user_id, order_id):
        return self.send_to_queue(str(order_id), 'payment-queue', json.dumps({
                'operation' : 'cancel_payment',
                'user_id' : user_id, 
                'order_id' : order_id}))

    def send_payment_status(self, user_id, order_id):
        return self.send_to_queue(str(order_id), 'payment-queue', json.dumps({
                'operation' : 'payment_status',
                'user_id' : user_id, 
                'order_id' : order_id}))
