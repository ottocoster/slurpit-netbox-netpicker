FROM python:3.11

RUN pip3 install requests
RUN pip3 install pytest
RUN pip3 install psycopg2-binary
RUN pip3 install python-dotenv

COPY *.py /tests/
WORKDIR /tests
