import os
import atexit

from flask import Flask
import pymongo

app = Flask("stock-service")

db: pymongo.MongoClient = pymongo.MongoClient(
    host=os.environ['MONGO_HOST'],
    port=int(os.environ['MONGO_PORT']),
    username=os.environ['MONGO_USERNAME'],
    password=os.environ['MONGO_PASSWORD'],
)


def close_db_connection():
    db.close()


atexit.register(close_db_connection)


@app.post('/item/create/<price>')
def create_item(price: int):
    pass


@app.get('/find/<item_id>')
def find_item(item_id: str):
    pass


@app.post('/add/<item_id>/<amount>')
def add_stock(item_id: str, amount: int):
    pass


@app.post('/subtract/<item_id>/<amount>')
def remove_stock(item_id: str, amount: int):
    pass
