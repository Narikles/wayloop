"""Planificateur intégré au processus web (hébergement en un seul processus, ex. offre gratuite Render).

Sans worker séparé, les refus programmés, relances, rappels, récapitulatifs et e-mails reçus
n'auraient personne pour les traiter. Ce fil d'exécution appelle la même boucle que le worker
(`worker.tick`) toutes les SCHEDULER_INTERVAL_SECONDS. Il ne démarre pas en tests ni quand un
worker séparé tourne (JOBS_MODE=worker), pour éviter les doubles envois.
"""
from __future__ import annotations

import logging
import threading

from .config import get_settings

log = logging.getLogger("wayloop.scheduler")
_thread: threading.Thread | None = None
_stop = threading.Event()


def enabled() -> bool:
    s = get_settings()
    return s.embedded_scheduler and s.jobs_mode == "inline" and s.environment != "test"


def _loop(interval: int) -> None:
    from .worker import tick

    last = 0.0
    while not _stop.wait(interval):
        last = tick(last, period=max(60, interval))


def start() -> None:
    global _thread
    if not enabled() or (_thread and _thread.is_alive()):
        return
    _stop.clear()
    interval = max(15, get_settings().scheduler_interval_seconds)
    _thread = threading.Thread(target=_loop, args=(interval,), name="wayloop-scheduler", daemon=True)
    _thread.start()
    log.info("Planificateur intégré démarré (toutes les %s s)", interval)


def stop() -> None:
    _stop.set()
