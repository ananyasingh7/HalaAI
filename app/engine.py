import asyncio
import logging
import time
from pathlib import Path

from mlx_lm import generate, load, stream_generate
from mlx_lm.sample_utils import make_sampler

from app.database import InferenceLog, init_db, log_stats
from app.logging_setup import setup_logging
from app.monitor import monitor

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

    async def generate_stream(self, request):
        """
        Generator that yields tokens in real-time.
        """
        async with self.lock:
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})
            
            prompt_formatted = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

            sampler = make_sampler(
                temp=getattr(request, "temp", 0.7),
                top_p=1.0,
                min_p=0.0,
                min_tokens_to_keep=1,
            )

            # --- [START] METRICS TRACKING ---
            start_time = time.time()
            tokens_generated = 0
            peak_gpu = 0.0
            peak_temp = 0.0
            response_text = ""
            
            # Calculate input token count (approximate cost tracking)
            prompt_tokens = len(self.tokenizer.encode(prompt_formatted))
            # -------------------------------

            # 2. Generation Loop
            for response in stream_generate(
                self.model, 
                self.tokenizer, 
                prompt=prompt_formatted, 
                max_tokens=request.max_tokens, 
                sampler=sampler,
            ):
                # Track volume
                tokens_generated += 1
                
                # Hardware poll: capture peaks during the heavy lifting
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

                yield response.text

            duration = time.time() - start_time
            final_stats = monitor.get_snapshot()
            
            # Create the log entry
            log_entry = InferenceLog(
                request_id=getattr(request, "request_id", "unknown"),
                adapter_name=self.adapter_id or "base",
                prompt=request.prompt,  # Optional: remove if privacy is a concern
                system_prompt=getattr(request, "system_prompt", None),
                response_text=response_text,
                tokens_in=prompt_tokens,
                tokens_out=tokens_generated,
                total_time_sec=duration,
                tokens_per_sec=tokens_generated / duration if duration > 0 else 0,
                
                # Hardware Vitals
                gpu_usage_pct=peak_gpu,
                gpu_temp_c=peak_temp,
                cpu_usage_pct=final_stats.get("cpu_usage", 0),
                ram_usage_pct=final_stats.get("ram_usage", 0),
                wattage=final_stats.get("gpu_power", 0),
                
                # Config
                model_name=self.model_id,
                temp=getattr(request, "temp", 0.7),
            )
            
            # Fire-and-forget save to SQLite
            asyncio.create_task(asyncio.to_thread(log_stats, log_entry))


# global instance
engine = ModelEngine()
