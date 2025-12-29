import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from mlx_lm import generate, load, stream_generate
from mlx_lm.sample_utils import make_sampler

from app.database import InferenceLog, init_db, log_stats
from app.logging_setup import setup_logging
from app.monitor import monitor

from app.queue import request_queue, QueueItem

setup_logging()
logger = logging.getLogger(__name__)

BASE_MODEL_ID = "mlx-community/Qwen2.5-14B-Instruct-4bit"
ADAPTERS_DIR = Path("adapters")

class ModelEngine:
    _instance = None

    def __new__(cls):
        # singleton pattern
        if cls._instance is None:
            # allocates a new instance of cls in memory and returns it
            cls._instance = super(ModelEngine, cls).__new__(cls) 
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        logger.info("Initializing Engine... Loading Base Model: %s", BASE_MODEL_ID)
        self.model_id = BASE_MODEL_ID
        self.adapter_id = None

        init_db()

        # use a Lock to prevent multiple apps from hitting GPU at the same exact time
        self.lock = asyncio.Lock()
        self._bg_lock = asyncio.Lock()
        self._worker_task = None
        self._monitor_task = None
        self.running = False
        self._monitor_interval = 5

        # load the base model
        self.model, self.tokenizer = load(self.model_id)
        self._initialized = True
        logger.info("Engine Online. Ready for inference.")

    def _resolve_adapter_path(self, adapter_name: str) -> Path:
        """
        Resolves an adapter name to a directory on disk.

        Supports:
        - A single adapter stored directly in `ADAPTERS_DIR` (use adapter_name="default")
        - Multiple adapters stored as subfolders under `ADAPTERS_DIR/<adapter_name>`
        """
        if adapter_name == "default":
            return ADAPTERS_DIR

        return ADAPTERS_DIR / adapter_name

    def load_adapter(self, adapter_name: str):
        """
        Hot-swaps the specialized brain (LoRA) without crashing RAM
        """
        if adapter_name in {"base", "none"}:
            self.unload_adapter()
            return

        adapter_path = self._resolve_adapter_path(adapter_name)
        if not adapter_path.exists():
            raise FileNotFoundError(f"Adapter {adapter_name} not found in {ADAPTERS_DIR}")
        
        if self.adapter_id == adapter_name:
            logger.info("Adapter %s already loaded.", adapter_name)
            return

        logger.info("Hot-swapping to adapter: %s...", adapter_name)

        # mlx efficient reload, re-fesus the base weights with the new adapter weights
        self.model, self.tokenizer = load(self.model_id, adapter_path=str(adapter_path))
        self.adapter_id = adapter_name
        logger.info("Swapped to %s", adapter_name)

    def unload_adapter(self):
        """
        Reverts to the base generic model
        """
        if self.adapter_id is None:
            return
        
        logger.info("Reverting adapter to base")
        self.model, self.tokenizer = load(self.model_id)
        self.adapter_id = None

    async def start_background_tasks(self):
        """
        Spins up the queue worker and monitor if they are not already running.
        """
        async with self._bg_lock:
            if self.running and self._worker_task and not self._worker_task.done():
                return

            self.running = True
            loop = asyncio.get_running_loop()

            if not self._worker_task or self._worker_task.done():
                self._worker_task = loop.create_task(self._worker_loop(), name="queue-worker")
                logger.info("Started background queue worker.")

            if not self._monitor_task or self._monitor_task.done():
                self._monitor_task = loop.create_task(self._queue_monitor_loop(), name="queue-monitor")
                logger.info("Started queue monitor.")

    async def shutdown(self):
        """
        Gracefully stop background tasks.
        """
        async with self._bg_lock:
            self.running = False
            tasks = [t for t in (self._worker_task, self._monitor_task) if t and not t.done()]
            for task in tasks:
                task.cancel()

        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _queue_monitor_loop(self):
        """
        Periodically log queue depth and wait times so we can watch it in server logs.
        """
        last_depth = None
        while self.running:
            try:
                stats = await request_queue.stats()
                depth = stats.get("depth", 0)

                if depth != last_depth or depth > 0:
                    logger.info(
                        "Queue status | depth=%s min_prio=%s max_prio=%s oldest_wait=%.2fs",
                        depth,
                        stats.get("min_priority"),
                        stats.get("max_priority"),
                        stats.get("oldest_wait", 0.0),
                    )
                last_depth = depth
            except asyncio.CancelledError:
                logger.info("Queue monitor stopped.")
                raise
            except Exception:
                logger.exception("Queue monitor error; retrying in %ss", self._monitor_interval)

            await asyncio.sleep(self._monitor_interval)

    async def _worker_loop(self):
        """
        The Consumer: Pulls from the queue and runs GPU inference.
        """
        logger.info("Queue worker loop running.")
        try:
            while self.running:
                job: QueueItem = await request_queue.dequeue()

                if not self.running:
                    break

                try:
                    req = job.payload["request"]
                    response_queue = job.payload["response_queue"]

                    # Prepare prompt
                    messages = []
                    if getattr(req, "system_prompt", None):
                        messages.append({"role": "system", "content": req.system_prompt})
                    messages.append({"role": "user", "content": req.prompt})

                    prompt_formatted = self.tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=True
                    )

                    sampler = make_sampler(
                        temp=getattr(req, "temp", 0.7),
                        top_p=1.0,
                        min_p=0.0,
                        min_tokens_to_keep=1,
                    )

                    async with self.lock:
                        start_time = time.time()
                        tokens_generated = 0
                        peak_gpu = 0.0
                        peak_temp = 0.0
                        response_text = ""
                        prompt_tokens = len(self.tokenizer.encode(prompt_formatted))

                        for response in stream_generate(
                            self.model,
                            self.tokenizer,
                            prompt=prompt_formatted,
                            max_tokens=req.max_tokens,
                            sampler=sampler,
                        ):
                            tokens_generated += 1

                            stats = monitor.get_snapshot()
                            if stats:
                                peak_gpu = max(peak_gpu, stats.get("gpu_usage", 0))
                                peak_temp = max(peak_temp, stats.get("gpu_temp", 0))

                            chunk = response.text or ""
                            if chunk:
                                if response_text and chunk.startswith(response_text):
                                    response_text = chunk
                                else:
                                    response_text += chunk

                            # Send token back to the specific client waiting
                            await response_queue.put(response.text)

                        duration = time.time() - start_time
                        final_stats = monitor.get_snapshot()

                    await response_queue.put(None)  # Signal completion

                    log_entry = InferenceLog(
                        request_id=job.request_id,
                        adapter_name=self.adapter_id or "base",
                        prompt=req.prompt,
                        system_prompt=getattr(req, "system_prompt", None),
                        response_text=response_text,
                        tokens_in=prompt_tokens,
                        tokens_out=tokens_generated,
                        total_time_sec=duration,
                        tokens_per_sec=tokens_generated / duration if duration > 0 else 0,
                        model_name=self.model_id,
                        temp=getattr(req, "temp", 0.7),
                        gpu_usage_pct=peak_gpu,
                        cpu_usage_pct=final_stats.get("cpu_usage", 0),
                        gpu_temp_c=peak_temp,
                        ram_usage_pct=final_stats.get("ram_usage", 0),
                        wattage=final_stats.get("gpu_power", 0),
                    )

                    asyncio.create_task(asyncio.to_thread(log_stats, log_entry))

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.exception("Error in job %s: %s", job.request_id, e)
                    try:
                        await job.payload["response_queue"].put(f"[ERROR: {e}]")
                        await job.payload["response_queue"].put(None)
                    except Exception:
                        logger.exception("Failed to notify client for job %s", job.request_id)
        except asyncio.CancelledError:
            logger.info("Queue worker cancelled.")
            raise
        except Exception:
            logger.exception("Queue worker crashed")
        finally:
            self.running = False

    async def generate_text(self, request):
        """
        The main inference method
        Protected by a lock to ensure serial processing.
        """
        async with self.lock:
            start_time = time.time()

            # format prompt
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})

            messages.append({"role": "user", "content": request.prompt})

            prompt_formatted = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

            response_text = generate(
                self.model,
                self.tokenizer,
                prompt=prompt_formatted,
                max_tokens=request.max_tokens,
                verbose=False
            )
            
            end_time = time.time()

            return {
                "text": response_text,
                "token_count": len(self.tokenizer.encode(response_text)),
                "processing_time": end_time - start_time
            }

    async def generate_stream(self, request) -> AsyncGenerator[str, None]:
        """
        The Producer: pushes a request into the queue and yields streamed tokens.
        """
        await self.start_background_tasks()

        response_queue: asyncio.Queue[str | None] = asyncio.Queue()
        request_id = str(uuid.uuid4())

        try:
            await request_queue.enqueue(
                request_id=request_id,
                priority=getattr(request, "priority", None),
                payload={
                    "request": request,
                    "response_queue": response_queue,
                },
            )
        except BufferError:
            raise RuntimeError("Request queue is full. Please retry shortly.")

        while True:
            token = await response_queue.get()
            if token is None:
                break
            yield token


# global instance
engine = ModelEngine()
