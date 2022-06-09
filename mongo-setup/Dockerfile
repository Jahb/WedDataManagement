FROM mongo:latest
RUN mkdir /config
WORKDIR /config
COPY wait-for-it.sh .
COPY mongo-setup.sh .
COPY mongo-changerepl.sh .
RUN chmod +x /config/wait-for-it.sh
RUN chmod +x /config/mongo-setup.sh
RUN chmod +x /config/mongo-changerepl.sh
CMD [ "sh", "-c", "/config/wait-for-it.sh order-db-service:27017 -- /config/mongo-setup.sh"]
CMD [ "sh", "-c", "/config/wait-for-it.sh stock-db-service:27017 -- /config/mongo-setup.sh"]
CMD [ "sh", "-c", "/config/wait-for-it.sh payment-db-service:27017 -- /config/mongo-setup.sh"]
