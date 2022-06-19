# Web-Scale Data Management Group 8

## How to deploy
Make sure you have minikube with ingress enabled.

To run the deploy script run `full-deploy.sh` from the root folder with the endpoint as an argument. So an example is: `./full-deploy.sh webdb.localdev.me`.
Pods may take some time to ready up.

If the K8 deployment is failing the service logic can still be tested with normal docker (If k8s is really not working :c ).
`docker-compose up --build`
You can use the localhost:8080 endpoint if not using k8s.

## Dockerhub image links:
https://hub.docker.com/repository/docker/jahb/stock
https://hub.docker.com/repository/docker/jahb/user
https://hub.docker.com/repository/docker/jahb/order


## Presentation Slides:
https://docs.google.com/presentation/d/1Im9FTw_gcACZJJlYyniGkALo5fJEtrssU_tJP6z-74k/edit#slide=id.gf41cfa9430_0_0

<!-- 



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

#### Local k8s Cluster



***Requirements:*** 
1. Make sure there is access to kubectl.
2. Make sure there is an image of all the Dockerfiles in this project. Where the names correspond to:
    * mongo -> weddatamanagementmongo:latest
    * mongo-setup -> weddatamanagementmongosetup
    * order -> order-service:latest
    * payment -> payment-service:latest
    * stock -> stock-service:latest
    !Step 2 not needed now it pulls from Jahb dockerhub repos
3. Setup the databases: 
    add helm repo: `helm repo add bitnami https://charts.bitnami.com/bitnami`
    payment-db: `helm install payment-db --set auth.rootPassword=mongo,architecture=replicaset,persistence.size=200Mi,persistence.enabled=true,readinessProbe.initialDelaySeconds=20,readinessProbe.timeoutSeconds=20 bitnami/mongodb`
    order-db: `helm install order-db --set auth.rootPassword=mongo,architecture=replicaset,persistence.size=200Mi,persistence.enabled=true,readinessProbe.initialDelaySeconds=20,readinessProbe.timeoutSeconds=20 bitnami/mongodb`
    stock-db: `helm install stock-db --set auth.rootPassword=mongo,architecture=replicaset,persistence.size=200Mi,persistence.enabled=true,readinessProbe.initialDelaySeconds=20,readinessProbe.timeoutSeconds=20 bitnami/mongodb`
4. run `kubectl apply -f ./k8s/ngninx-ingress-controller.yaml` Which spawnsthe nginx ingress controller inside another namespace.
5. run `kubectl apply -f ./k8s/services-deployment.yaml` which spins up all the flask api's and the nginx gateway.  
6. Forward the port: `kubectl port-forward --namespace=ingress-nginx service/ingress-nginx-controller 8080:80`
7. goto webdb.localdev.me:8080 to access the services.


Resources: https://kubernetes.github.io/ingress-nginx/deploy/#quick-start
Using minikube ingress might be manually enabled.
`kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.2.0/deploy/static/provider/cloud/deploy.yaml`


*** OLD minikube (local k8s cluster) ***

This setup is for local k8s testing to see if your k8s config works before deploying to the cloud. 
First deploy your database using helm by running the `deploy-charts-minicube.sh` file (in this example the DB is Redis 
but you can find any database you want in https://artifacthub.io/ and adapt the script). Then adapt the k8s configuration files in the
`\k8s` folder to mach your system and then run `kubectl apply -f .` in the k8s folder. 

***Requirements:*** You need to have minikube (with ingress enabled) and helm installed on your machine.

#### kubernetes cluster (managed k8s cluster in the cloud)

Similarly to the `minikube` deployment but run the `deploy-charts-cluster.sh` in the helm step to also install an ingress to the cluster. 

***Requirements:*** You need to have access to kubectl of a k8s cluster. -->
