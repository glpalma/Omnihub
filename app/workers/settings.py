from arq.connections import RedisSettings

from app.core.config import settings
from app.workers.tasks import process_inbound_message, process_whatsapp_message


class WorkerSettings:
    """ARQ worker configuration.

    The `functions` list registers every task the worker knows how to run.
    The string name used in enqueue_job() must match the function name here.
    """

    functions = [process_whatsapp_message, process_inbound_message]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_tries = 3  # retry up to 3 times on transient failures
    job_timeout = 30  # seconds per task before ARQ considers it timed out
