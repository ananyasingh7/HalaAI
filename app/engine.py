from pathlib import Path
from mlx_lm import load, generate, stream_generate
from mlx_lm.sample_utils import make_sampler
import asyncio
import time

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
        
        print(f"Initializing Engine... Loading Base Model: {BASE_MODEL_ID}")
        self.model_id = BASE_MODEL_ID
        self.adapter_id = None

        # use a Lock to prevent multiple apps from hitting GPU at the same exact time
        self.lock = asyncio.Lock()

        # load the base model
        self.model, self.tokenizer = load(self.model_id)
        self._initialized = True
        print("Engine Online. Ready for inference.")

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
            print(f"Adapter {adapter_name} already loaded.")
            return

        print(f"Hot-swapping to adapter: {adapter_name}...")

        # mlx efficient reload, re-fesus the base weights with the new adapter weights
        self.model, self.tokenizer = load(self.model_id, adapter_path=str(adapter_path))
        self.adapter_id = adapter_name
        print(f"Swapped to {adapter_name}")

    def unload_adapter(self):
        """
        Reverts to the base generic model
        """
        if self.adapter_id is None:
            return
        
        print("Reverting adapter to base")
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

            # stream generation
            # mlx_lm.stream_generate yields (token, text_so_far)
            # We filter to just send the new text chunks
            sampler = make_sampler(
                temp=getattr(request, "temp", 0.7),
                top_p=1.0,
                min_p=0.0,
                min_tokens_to_keep=1,
            )

            for response in stream_generate(
                self.model, 
                self.tokenizer, 
                prompt=prompt_formatted, 
                max_tokens=request.max_tokens, 
                sampler=sampler,
            ):
                yield response.text


# global instance
engine = ModelEngine()
