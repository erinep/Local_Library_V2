from __future__ import annotations

import os

from redis import Redis
from rq import Queue

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_QUEUE_NAME = "metadata"
DEFAULT_JOB_TIMEOUT = 6 * 60 * 60


def get_redis_url() -> str:
    return os.getenv("REDIS_URL", DEFAULT_REDIS_URL)


def get_queue_name() -> str:
    return os.getenv("RQ_QUEUE_NAME", DEFAULT_QUEUE_NAME)


def get_redis_connection() -> Redis:
    return Redis.from_url(get_redis_url())


def get_queue() -> Queue:
    return Queue(
        get_queue_name(),
        connection=get_redis_connection(),
        default_timeout=DEFAULT_JOB_TIMEOUT,
    )
