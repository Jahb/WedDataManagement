#!/usr/bin/env bash

helm repo add bitnami https://charts.bitnami.com/bitnami

helm repo update

helm install payment-db --set auth.rootPassword=mongo,architecture=replicaset,persistence.enabled=true,readinessProbe.initialDelaySeconds=20,readinessProbe.timeoutSeconds=20 bitnami/mongodb
helm install order-db --set auth.rootPassword=mongo,architecture=replicaset,persistence.enabled=true,readinessProbe.initialDelaySeconds=20,readinessProbe.timeoutSeconds=20 bitnami/mongodb
helm install stock-db --set auth.rootPassword=mongo,architecture=replicaset,persistence.enabled=true,readinessProbe.initialDelaySeconds=20,readinessProbe.timeoutSeconds=20 bitnami/mongodb

echo "Waiting for DBs to be ready (30 seconds)..."
sleep 30s
echo "Applying KubeCTL deployments"
kubectl apply -f ./k8s/services-deployment.yaml
echo "Portforwarding system available at: http://webdb.localdev.me:8080"
kubectl port-forward --namespace=ingress-nginx service/ingress-nginx-controller 8080:80