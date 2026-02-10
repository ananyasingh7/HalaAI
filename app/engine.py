import asyncio
import gc
import logging
import platform
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from mlx_lm import generate, load, stream_generate
from mlx_lm.sample_utils import make_sampler

from app.config import settings
from app.database import InferenceLog, init_db, log_stats
from app.logging_setup import setup_logging
from app.monitor import monitor

from app.queue import request_queue, QueueItem
from app.text_utils import strip_thinking

setup_logging()
logger = logging.getLogger(__name__)

BASE_MODEL_ID = "mlx-community/Qwen3-30B-A3B-4bit"
ADAPTERS_DIR = Path("adapters")
BYTES_PER_GB = 1024**3

class ModelEngine:
    """Singleton GPU engine that manages adapters, queues, and inference."""
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

        self._configure_metal_wired_limit()

        # load the base model
        self.model, self.tokenizer = load(self.model_id)
        self._initialized = True
        logger.info("Engine Online. Ready for inference.")

    def _apply_chat_template(self, messages: list[dict], disable_thinking: bool = False) -> str:
        """
        Use the tokenizer chat template while disabling Qwen3 "thinking" output when supported.
        Falls back to the legacy signature for older tokenizers.
        """
        if disable_thinking:
            try:
                return self.tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
                )
            except TypeError:
                return self.tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
        return self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

    def _strip_thinking(self, text: str) -> str:
        return strip_thinking(text)

    def _configure_metal_wired_limit(self) -> None:
        cfg = settings.engine_memory
        if not cfg.enable_metal_wired_limit:
            return

        try:
            import mlx.core as mx
        except Exception:
            logger.exception("Failed to import mlx.core; skipping wired memory limit setup.")
            return

        try:
            if not hasattr(mx, "metal") or not mx.metal.is_available():
                logger.info("Metal not available; skipping wired memory limit setup.")
                return

            info = mx.metal.device_info()
            recommended_limit = int(info.get("max_recommended_working_set_size", 0))
            if recommended_limit <= 0:
                logger.info("Could not resolve recommended Metal working set size; skipping wired limit.")
                return

            if cfg.metal_wired_limit_gb is not None and cfg.metal_wired_limit_gb > 0:
                target_limit = int(cfg.metal_wired_limit_gb * BYTES_PER_GB)
            else:
                ratio = max(0.1, min(cfg.metal_wired_limit_ratio, 1.0))
                target_limit = int(recommended_limit * ratio)

            safe_limit = max(1, min(target_limit, recommended_limit))
            previous_limit = mx.set_wired_limit(safe_limit)
            logger.info(
                "Configured MLX wired limit to %.2fGB (previous %.2fGB, recommended %.2fGB, platform=%s).",
                safe_limit / BYTES_PER_GB,
                previous_limit / BYTES_PER_GB,
                recommended_limit / BYTES_PER_GB,
                platform.mac_ver()[0] or "unknown",
            )
        except Exception:
            logger.exception("Failed to configure MLX wired memory limit.")

    def _kv_generation_kwargs(self) -> dict:
        cfg = settings.engine_memory
        kwargs = {}
        if cfg.max_kv_size and cfg.max_kv_size > 0:
            kwargs["max_kv_size"] = int(cfg.max_kv_size)
        if cfg.kv_bits is not None:
            kwargs["kv_bits"] = int(cfg.kv_bits)
            kwargs["kv_group_size"] = int(cfg.kv_group_size)
            kwargs["quantized_kv_start"] = int(cfg.quantized_kv_start)
        return kwargs

    def _max_prompt_tokens_for_request(self, requested_max_tokens: int) -> int | None:
        cfg = settings.engine_memory
        caps: list[int] = []
        if cfg.max_prompt_tokens and cfg.max_prompt_tokens > 0:
            caps.append(int(cfg.max_prompt_tokens))
        if cfg.max_kv_size and cfg.max_kv_size > 0:
            kv_cap = int(cfg.max_kv_size) - int(requested_max_tokens) - int(cfg.prompt_token_reserve)
            if kv_cap > 0:
                caps.append(kv_cap)
        return min(caps) if caps else None

    def _truncate_prompt_tokens(self, prompt_tokens: list[int], limit: int) -> tuple[list[int], bool]:
        if limit <= 0 or len(prompt_tokens) <= limit:
            return prompt_tokens, False

        keep_head = min(settings.engine_memory.preserve_prompt_head_tokens, max(limit - 1, 0))
        if keep_head <= 0:
            return prompt_tokens[-limit:], True

        keep_tail = limit - keep_head
        if keep_tail <= 0:
            return prompt_tokens[:limit], True

        return prompt_tokens[:keep_head] + prompt_tokens[-keep_tail:], True

    def _prepare_prompt_and_limits(self, request, prompt_formatted: str) -> dict:
        requested_max_tokens = max(1, int(getattr(request, "max_tokens", 256)))
        encoded_prompt = self.tokenizer.encode(prompt_formatted)
        original_prompt_tokens = len(encoded_prompt)

        prompt_limit = self._max_prompt_tokens_for_request(requested_max_tokens)
        truncated = False
        if prompt_limit is not None and original_prompt_tokens > prompt_limit:
            encoded_prompt, truncated = self._truncate_prompt_tokens(encoded_prompt, prompt_limit)
            logger.warning(
                "Prompt trimmed from %s to %s tokens to stay within memory limits.",
                original_prompt_tokens,
                len(encoded_prompt),
            )

        final_max_tokens = requested_max_tokens
        cfg = settings.engine_memory
        if cfg.max_kv_size and cfg.max_kv_size > 0:
            kv_available_for_generation = int(cfg.max_kv_size) - len(encoded_prompt) - int(cfg.prompt_token_reserve)
            if kv_available_for_generation < 1:
                hard_prompt_limit = max(1, int(cfg.max_kv_size) - int(cfg.prompt_token_reserve) - 1)
                encoded_prompt, _ = self._truncate_prompt_tokens(encoded_prompt, hard_prompt_limit)
                kv_available_for_generation = max(
                    1,
                    int(cfg.max_kv_size) - len(encoded_prompt) - int(cfg.prompt_token_reserve),
                )

            if final_max_tokens > kv_available_for_generation:
                logger.info(
                    "Capping max_tokens from %s to %s to respect max_kv_size=%s.",
                    final_max_tokens,
                    kv_available_for_generation,
                    cfg.max_kv_size,
                )
                final_max_tokens = kv_available_for_generation

        return {
            "prompt": encoded_prompt,
            "prompt_tokens": len(encoded_prompt),
            "max_tokens": final_max_tokens,
            "prompt_was_trimmed": truncated,
        }

    def _post_request_cleanup(self) -> None:
        if settings.engine_memory.force_gc_after_request:
            gc.collect()

    def _strip_thinking_stream(self, text: str, in_think: bool) -> tuple[str, bool]:
        """
        Strip <think>...</think> spans from a streamed chunk, preserving state across chunks.
        Returns (clean_text, in_think_state).
        """
        if not text:
            return "", in_think

        out = []
        i = 0
        while i < len(text):
            if in_think:
                end = text.find("</think>", i)
                if end == -1:
                    return "".join(out), True
                i = end + len("</think>")
                if i < len(text) and text[i] == "\n":
                    i += 1
                in_think = False
                continue

            start = text.find("<think>", i)
            if start == -1:
                out.append(text[i:])
                return "".join(out), False
            out.append(text[i:start])
            i = start + len("<think>")
            in_think = True

        return "".join(out), in_think

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

                    prompt_formatted = self._apply_chat_template(
                        messages, disable_thinking=getattr(req, "_disable_thinking", False)
                    )
                    generation_inputs = self._prepare_prompt_and_limits(req, prompt_formatted)

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
                        clean_response_text = ""
                        last_clean = ""
                        prompt_tokens = generation_inputs["prompt_tokens"]

                        for response in stream_generate(
                            self.model,
                            self.tokenizer,
                            prompt=generation_inputs["prompt"],
                            max_tokens=generation_inputs["max_tokens"],
                            sampler=sampler,
                            **self._kv_generation_kwargs(),
                        ):
                            tokens_generated += 1

                            stats = monitor.get_snapshot()
                            if stats:
                                peak_gpu = max(peak_gpu, stats.get("gpu_usage", 0))
                                peak_temp = max(peak_temp, stats.get("gpu_temp", 0))

                            chunk = response.text or ""
                            if chunk:
                                # stream_generate can emit cumulative text; keep the latest full response.
                                if response_text and chunk.startswith(response_text):
                                    response_text = chunk
                                else:
                                    response_text += chunk

                            stripped = self._strip_thinking(response_text)
                            if stripped.startswith(last_clean):
                                clean_delta = stripped[len(last_clean):]
                            else:
                                clean_delta = stripped
                            last_clean = stripped
                            if clean_delta:
                                clean_response_text += clean_delta
                                await response_queue.put(clean_delta)

                        duration = time.time() - start_time
                        final_stats = monitor.get_snapshot()

                    tps = tokens_generated / duration if duration > 0 else 0
                    logger.info(
                        "Finished job %s in %.2fs | Speed: %.1f t/s | RAM: Process=%.1fGB System=%.1fGB",
                        job.request_id,
                        duration,
                        tps,
                        final_stats.get("process_ram_gb", 0),
                        final_stats.get("system_ram_gb", 0),
                    )

                    await response_queue.put(None)  # Signal completion

                    log_entry = InferenceLog(
                        request_id=job.request_id,
                        adapter_name=self.adapter_id or "base",
                        prompt=req.prompt,
                        system_prompt=getattr(req, "system_prompt", None),
                        response_text=clean_response_text or self._strip_thinking(response_text),
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
                finally:
                    self._post_request_cleanup()
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
            try:
                # format prompt
                messages = []
                if request.system_prompt:
                    messages.append({"role": "system", "content": request.system_prompt})

                messages.append({"role": "user", "content": request.prompt})

                prompt_formatted = self._apply_chat_template(
                    messages, disable_thinking=getattr(request, "_disable_thinking", False)
                )
                generation_inputs = self._prepare_prompt_and_limits(request, prompt_formatted)

                response_text = generate(
                    self.model,
                    self.tokenizer,
                    prompt=generation_inputs["prompt"],
                    max_tokens=generation_inputs["max_tokens"],
                    verbose=False,
                    **self._kv_generation_kwargs(),
                )

                response_text = self._strip_thinking(response_text)
                
                end_time = time.time()
                return {
                    "text": response_text,
                    "token_count": len(self.tokenizer.encode(response_text)),
                    "processing_time": end_time - start_time
                }
            finally:
                self._post_request_cleanup()

    async def generate_stream(self, request) -> AsyncGenerator[str, None]:
        """
        The Producer: pushes a request into the queue and yields streamed tokens.
        """
        await self.start_background_tasks()

        # Each request has its own response queue to stream tokens back to the caller.
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
