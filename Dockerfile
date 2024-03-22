# it's offical so i'm using it + alpine so damn small
FROM python:3.8.3-alpine3.10

# copy the codebase
COPY . /www
RUN chmod +x /www/manager.py

RUN /usr/local/bin/python -m pip install --upgrade pip
RUN pip install wheel
RUN pip3 install --no-build-isolation "Cython<3" "pyyaml==5.4.1"

# install required packages - requires build-base due to gevent GCC complier requirements
RUN apk add --no-cache build-base libffi-dev
RUN pip install -r /www/requirements.txt

# adding the gunicorn config
COPY config/config.py /etc/gunicorn/config.py

#set python to be unbuffered
ENV PYTHONUNBUFFERED=1

#exposing the port
EXPOSE 80

# and running it
CMD ["gunicorn" ,"--config", "/etc/gunicorn/config.py", "manager:app"]

#ENTRYPOINT ["tail", "-f", "/dev/null"]