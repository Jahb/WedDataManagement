# touch abc.txt
echo "=========================== running run.sh"

sleep 10
mongo --eval "rs.initiate()" --username root --password mongo
