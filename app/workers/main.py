import logging
import signal
import threading
import time
from redis import Redis
from rq import Worker, Queue

from app.core.config import settings
from app.workers.tasks import run_process_due_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker] %(message)s"
)
logger = logging.getLogger("whatsapp-worker")


def run_due_jobs_scheduler_loop(
    interval_seconds: int = 60,
    stop_event: threading.Event | None = None
) -> None:
    """
    Loop periódico que executa o processamento de lembretes e jobs devidos (scheduled_at <= now).
    Roda desacoplado em uma thread de background junto ao worker.
    """
    logger.info("Iniciando scheduler periódico de lembretes (intervalo: %ds)...", interval_seconds)
    while stop_event is None or not stop_event.is_set():
        try:
            count = run_process_due_jobs()
            if count > 0:
                logger.info("Scheduler de lembretes processou %d job(s) pendente(s).", count)
        except Exception as exc:
            logger.error("Erro no scheduler periódico de lembretes: %s", exc)

        if stop_event:
            if stop_event.wait(timeout=interval_seconds):
                break
        else:
            time.sleep(interval_seconds)

    logger.info("Scheduler periódico de lembretes finalizado.")


def run_rq_worker():
    logger.info("Conectando worker ao Redis em: %s", settings.REDIS_URL)
    stop_event = threading.Event()

    def handle_shutdown(signum, frame):
        logger.info("Sinal %s recebido. Encerrando worker e scheduler...", signum)
        stop_event.set()

    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                signal.signal(sig, handle_shutdown)
            except (ValueError, OSError):
                pass

    # Inicia a thread periódica de scheduler
    interval = getattr(settings, "SCHEDULER_INTERVAL_SECONDS", 60)
    scheduler_thread = threading.Thread(
        target=run_due_jobs_scheduler_loop,
        kwargs={"interval_seconds": interval, "stop_event": stop_event},
        name="DueJobsScheduler",
        daemon=True
    )
    scheduler_thread.start()

    try:
        redis_conn = Redis.from_url(settings.REDIS_URL)
        queues = ["high", "default", "low", "automations"]
        worker = Worker(
            [Queue(name, connection=redis_conn) for name in queues],
            connection=redis_conn
        )
        logger.info("Worker pronto para processar filas: %s", ", ".join(queues))
        worker.work(with_scheduler=True)
    except Exception as exc:
        logger.error("Erro no worker: %s. Aguardando reconexão...", exc)
    finally:
        stop_event.set()


if __name__ == "__main__":
    run_rq_worker()
