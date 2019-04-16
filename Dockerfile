FROM python:2.7


RUN mkdir -p /app
WORKDIR /app
COPY requirements.docker.txt /app
RUN pip install --no-cache-dir -r requirements.docker.txt 

VOLUME /data
EXPOSE 12345

CMD ["browsepy", "--directory" , "/data", "0.0.0.0" , "12345"]
