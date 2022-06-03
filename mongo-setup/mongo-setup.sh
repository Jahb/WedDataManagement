mongo mongodb://order-db-service:27017 --eval "rs.initiate(); rs.status()" --username root --password mongo
mongo mongodb://stock-db-service:27017 --eval "rs.initiate(); rs.status()" --username root --password mongo
mongo mongodb://payment-db-service:27017 --eval "rs.initiate(); rs.status()" --username root --password mongo
