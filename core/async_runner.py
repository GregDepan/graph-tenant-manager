"""
Exécuteur async persistant pour Graph Tenant Manager.

Fix critique : le SDK Graph garde ses connexions HTTP liées à l'event loop
où il a été créé. En appelant asyncio.run() plusieurs fois (une par requête),
l'ancien code provoquait "Event loop is closed" dès la deuxième requête.

Solution : UN SEUL event loop qui vit dans un thread dédié, utilisé pour
toutes les opérations async pendant toute la durée de l'application.
"""

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Callable, Coroutine, Optional


class AsyncRunner:
    """
    Event loop persistant dans un thread séparé.

    Usage :
        runner = AsyncRunner()
        result = runner.run(coro)          # bloquant (depuis un thread de travail)
        runner.run_in_thread(coro, cb)     # non-bloquant avec callback (depuis la GUI)
    """

    _instance: Optional["AsyncRunner"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()
        self._stopping = False

    # ---------- Singleton ----------

    @classmethod
    def get_instance(cls) -> "AsyncRunner":
        with cls._lock:
            if cls._instance is None:
                cls._instance = AsyncRunner()
            return cls._instance

    # ---------- Cycle de vie ----------

    def start(self) -> None:
        """Démarre le thread + event loop (idempotent)."""
        if self._started.is_set():
            return
        self._stopping = False
        self._thread = threading.Thread(
            target=self._thread_main, name="AsyncRunner", daemon=True
        )
        self._thread.start()
        self._started.wait(timeout=10)

    def stop(self) -> None:
        """Arrête proprement l'event loop et le thread."""
        if not self._started.is_set():
            return
        self._stopping = True
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self._schedule_stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._started.clear()

    def _schedule_stop(self) -> None:
        asyncio.get_event_loop().stop()

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._started.set()

        try:
            self._loop.run_forever()
        finally:
            # Nettoyage des tâches restantes
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            except Exception:
                pass
            self._loop.close()

    # ---------- Exécution ----------

    def run(self, coro: Coroutine) -> Any:
        """
        Exécute une coroutine dans le loop persistant et attend le résultat.
        À appeler depuis un thread de travail (PAS depuis le thread Tkinter
        si la coroutine est longue).
        """
        self.start()
        loop = self._loop
        if loop is None:
            raise RuntimeError("AsyncRunner: event loop non démarré")
        future: Future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=300)  # 5 min max par opération

    def run_in_thread(
        self,
        coro_factory: Callable[[], Any],
        callback: Optional[Callable[[Any], None]] = None,
        error_callback: Optional[Callable[[Exception], None]] = None,
    ) -> threading.Thread:
        """
        Exécute une factory en arrière-plan, SANS bloquer la GUI.

        La factory peut retourner :
        - une coroutine → exécutée dans l'event loop persistant
        - une valeur directe (fonction sync) → retournée telle quelle
        Utile pour mélanger appels async (services Graph) et appels
        bloquants sync (authentification MSAL) dans la même mécanique.

        Args:
            coro_factory: fonction (lambda) appelée dans le thread
            callback: appelé avec le résultat
            error_callback: appelé avec l'exception
        """
        def worker():
            try:
                produced = coro_factory()
                if asyncio.iscoroutine(produced):
                    result = self.run(produced)
                else:
                    result = produced
                if callback:
                    callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)
                else:
                    raise

        t = threading.Thread(target=worker, daemon=True, name="GraphTask")
        t.start()
        return t

    @property
    def is_running(self) -> bool:
        return self._started.is_set() and self._loop is not None and self._loop.is_running()