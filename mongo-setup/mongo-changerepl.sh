mongo mongodb://order-db-service:27017 --eval "rs.initiate();" --username root --password mongo
mongo mongodb://stock-db-service:27017 --eval "rs.initiate();" --username root --password mongo
mongo mongodb://payment-db-service:27017 --eval "rs.initiate();" --username root --password mongo
sleep 15s
mongo mongodb://order-db-service:27017 --eval "var cfg = rs.conf(); cfg.members[0].host='order-db-service:27017'; rs.reconfig(cfg);" --username root --password mongo
mongo mongodb://stock-db-service:27017 --eval "var cfg = rs.conf(); cfg.members[0].host='stock-db-service:27017'; rs.reconfig(cfg);" --username root --password mongo
mongo mongodb://payment-db-service:27017 --eval "var cfg = rs.conf(); cfg.members[0].host='payment-db-service:27017'; rs.reconfig(cfg);" --username root --password mongo

