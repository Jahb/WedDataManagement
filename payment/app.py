import os
import atexit

from flask import Flask
import pymongo


app = Flask("payment-service")

db: pymongo.MongoClient = pymongo.MongoClient(
    host=os.environ['MONGO_HOST'],
    port=int(os.environ['MONGO_PORT']),
    username=os.environ['MONGO_USERNAME'],
    password=os.environ['MONGO_PASSWORD'],
)

def close_db_connection():
    db.close()


atexit.register(close_db_connection)


@app.post('/create_user')
def create_user():
    pass


@app.get('/find_user/<user_id>')
def find_user(user_id: str):
    pass


@app.post('/add_funds/<user_id>/<amount>')
def add_credit(user_id: str, amount: int):
    pass


@app.post('/pay/<user_id>/<order_id>/<amount>')
def remove_credit(user_id: str, order_id: str, amount: int):
    # only update the doc if:
    # * it is still in the original stat

    


    """
    idea:
     * create table "payments" and table "barrier" (or completed ops)
     * run a transaction, update the payment table and insert order_id into barrier
       * if order_id is already in barrier, insert fails and so the transaction fails
       * if order_id is not already in barrier, it is added. 
     * if we want to undo a transaction, we can create a transaction where we update the payment table
       and remove order_id from barrier.  
       * if order_id is already in barrier, remove succeeds and so the transaction succeeds
       * if order_id is not already in barrier, remove fails and so the revert fails too.

    ```
    test> db.barrier.insertOne({"_id": "aaa"})
    { acknowledged: true, insertedId: 'aaa' }
    test> db.barrier.insertOne({"_id": "aaa"})
    MongoServerError: E11000 duplicate key error collection: test.barrier index: _id_ dup key: { _id: "aaa" }



db.createCollection("test")
db.createCollection("barrier")

session = db.getMongo().startSession( { readPreference: { mode: "primary" } } );
session.startTransaction( { readConcern: { level: "snapshot" }, writeConcern: { w: "majority" } } );
    session.getDatabase("db").test.insertOne({"x": "ccc"})
    session.getDatabase("db").barrier.insertOne({"_id": "ccc"})
session.commitTransaction(); 

    ```
 
    """


@app.post('/cancel/<user_id>/<order_id>')
def cancel_payment(user_id: str, order_id: str):
    pass


@app.post('/status/<user_id>/<order_id>')
def payment_status(user_id: str, order_id: str):
    pass
