# touch abc.txt
echo "a=========================== running arun.sh"

/docker-entrypoint-initdb.d/run.sh & # run in background
