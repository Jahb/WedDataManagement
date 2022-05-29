mongo mongodb://order-db:27017 --eval "rs.initiate(); rs.status()" --username root --password mongo
mongo mongodb://stock-db:27017 --eval "rs.initiate(); rs.status()" --username root --password mongo
mongo mongodb://payment-db:27017 --eval "rs.initiate(); rs.status()" --username root --password mongo
