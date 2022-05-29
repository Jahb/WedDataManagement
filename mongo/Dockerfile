FROM mongo
RUN  mkdir keyfiles
RUN openssl rand -base64 756 > keyfiles/order-keyfile
RUN openssl rand -base64 756 > keyfiles/payment-keyfile
RUN openssl rand -base64 756 > keyfiles/stock-keyfile
RUN chmod 400 keyfiles/*
RUN chown 999:999 keyfiles/*      
RUN chown -R mongodb:mongodb keyfiles/*
