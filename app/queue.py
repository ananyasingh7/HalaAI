import asyncio
import heapq
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from app.config import settings, QueueConfig

import logging
from app.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

@dataclass(order=True)
class QueueItem:
    priority: int
    entry_time: float
    request_id: str = field(compare=False)
    payload: Any = field(compare=False)
    
    # hidden field to track waiting time
    # use this to prevent starvation if configured
    original_priority: int = field(compare=False, default=10)

class Queue:
    def __init__(self, config: Optional[QueueConfig] = None):
        self._heap = []
        self._event = asyncio.Event()
        self._lock = asyncio.Lock()
        self.config = config or settings.queue

    async def enqueue(self, request_id: str, payload: Any, priority: Optional[int] = None):
        """
        Adds an item to the queue. 
        Lower priority number = Higher importance (0 is VIP).
        """
        async with self._lock:
            # Check limits
            if len(self._heap) >= self.config.max_size:
                logger.info(f"Queue full! Max size: {self.config.max_size}")
                raise BufferError()

            # Use default priority if not provided
            priority_value = priority if priority is not None else self.config.default_priority

            item = QueueItem(
                priority=priority_value,
                original_priority=priority_value,
                entry_time=time.time(),
                request_id=request_id,
                payload=payload
            )
            
            heapq.heappush(self._heap, item)
            self._event.set() # wake up the worker
            logger.info(f"Enqueued {request_id} (Priority {priority_value}). Depth: {len(self._heap)}")

    async def dequeue(self) -> QueueItem:
        """
        Blocks until an item is available, then returns the highest priority one.
        """
        while True:
            # Wait efficiently without spinning CPU
            await self._event.wait()
            
            async with self._lock:
                if not self._heap:
                    self._event.clear()
                    continue
                
                # Starvation Check (Optional Feature)
                if self.config.starvation_prevention:
                    self._aging_check()

                # Pop highest priority (lowest number)
                item = heapq.heappop(self._heap)
                
                if not self._heap:
                    self._event.clear()
                    
                return item

    def _aging_check(self):
        """
        iterate through heap and boost priority of old items.
        expensive operation O(N) only run if necessary.
        """
        now = time.time()
        modified = False
        
        for item in self._heap:
            wait_time = now - item.entry_time
            if wait_time > self.config.aging_interval_sec:
                # boost priority by 1 for every interval waited
                boost = int(wait_time / self.config.aging_interval_sec)
                new_prio = max(0, item.original_priority - boost)
                
                if new_prio != item.priority:
                    item.priority = new_prio
                    modified = True
        
        if modified:
            heapq.heapify(self._heap)

    async def stats(self) -> Dict[str, Any]:
        """
        Snapshot of current queue health for monitoring purposes.
        """
        async with self._lock:
            now = time.time()
            oldest_wait = max((now - item.entry_time) for item in self._heap) if self._heap else 0.0
            priorities = [item.priority for item in self._heap]
            return {
                "depth": len(self._heap),
                "min_priority": min(priorities, default=None),
                "max_priority": max(priorities, default=None),
                "oldest_wait": oldest_wait,
            }

    def __len__(self) -> int:
        return len(self._heap)

request_queue = Queue()
