from arq.connections import RedisSettings

from app.core.config import settings
from app.workers.tasks import process_inbound_message, run_bot_turn


class WorkerSettings:
    """ARQ worker configuration.

    The `functions` list registers every task the worker knows how to run.
    The string name used in enqueue_job() must match the function name here.
    """

    functions = [process_inbound_message, run_bot_turn]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_tries = 3 # retry up to 3 times on transient failures
    job_timeout = 60 # seconds per task before ARQ considers it timed out
    # The bot turn uses one job id per ticket so a burst of messages collapses
    # into a single run. Keeping the result would block the next turn for an hour.
    keep_result = 0
