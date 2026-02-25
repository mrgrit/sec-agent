import os
from redis import Redis
from rq import Worker, Queue, Connection
from app.core.config import settings
from app.core.db import init_db

LISTEN = ["default"]


def main():
    init_db()
    redis_conn = Redis.from_url(settings.REDIS_URL)
    with Connection(redis_conn):
        worker = Worker(map(Queue, LISTEN))
        worker.work()


if __name__ == "__main__":
    main()
