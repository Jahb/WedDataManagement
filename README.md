# Web-scale Data Management Project Template

Basic project structure with Python's Flask and Redis. 
**You are free to use any web framework in any language and any database you like for this project.**


To use the databases, you need to generate keyfiles for each DB.

```
mkdir keyfiles
openssl rand -base64 756 > keyfiles/order-keyfile
openssl rand -base64 756 > keyfiles/payment-keyfile
openssl rand -base64 756 > keyfiles/stock-keyfile
chmod 400 keyfiles/*
chown 999:999 keyfiles/*
```

To start up the docker container:
```commandline
docker-compose up --build
```

To connect to one of the running MongoDB instances:

1. First, start up the docker container
2. Then run the mongosh command on the desired DB image, one of `{payment,stock,order}-db`.
    ```commandline
   docker exec -it payment-db mongosh --username root --password mongo
   ```
   You are now connected and authenticated with the payment db.

To run the python tests,

1. First, start up the docker container
2. Then run
   ```commandline
   python test/test_microservices.py
   ```

### Project structure

* `env`
    Folder containing the Redis env variables for the docker-compose deployment
    
* `helm-config` 
   Helm chart values for Redis and ingress-nginx
        
* `k8s`
    Folder containing the kubernetes deployments, apps and services for the ingress, order, payment and stock services.
    
* `order`
    Folder containing the order application logic and dockerfile. 
    
* `payment`
    Folder containing the payment application logic and dockerfile. 

* `stock`
    Folder containing the stock application logic and dockerfile. 

* `test`
    Folder containing some basic correctness tests for the entire system. (Feel free to enhance them)

### Deployment types:

#### docker-compose (local development)

After coding the REST endpoint logic run `docker-compose up --build` in the base folder to test if your logic is correct
(you can use the provided tests in the `\test` folder and change them as you wish). 

***Requirements:*** You need to have docker and docker-compose installed on your machine.

#### minikube (local k8s cluster)

This setup is for local k8s testing to see if your k8s config works before deploying to the cloud. 
First deploy your database using helm by running the `deploy-charts-minicube.sh` file (in this example the DB is Redis 
but you can find any database you want in https://artifacthub.io/ and adapt the script). Then adapt the k8s configuration files in the

(For windows atleast -jah) `minikube image load stock:latest` for every docker container

`\k8s` folder to mach your system and then run `kubectl apply -f .` in the k8s folder. 

***Requirements:*** You need to have minikube (with ingress enabled) and helm installed on your machine.

#### kubernetes cluster (managed k8s cluster in the cloud)

Similarly to the `minikube` deployment but run the `deploy-charts-cluster.sh` in the helm step to also install an ingress to the cluster. 

***Requirements:*** You need to have access to kubectl of a k8s cluster.
