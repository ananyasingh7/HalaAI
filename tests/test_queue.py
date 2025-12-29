import asyncio
import unittest

from app.config import QueueConfig
from app.queue import Queue


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_priority_ordering(self):
        queue = Queue(
            QueueConfig(
                max_size=10,
                starvation_prevention=False,
                aging_interval_sec=60,
                default_priority=10,
            )
        )

        await queue.enqueue("standard", payload={}, priority=10)
        await queue.enqueue("vip", payload={}, priority=1)

        first = await asyncio.wait_for(queue.dequeue(), timeout=0.5)
        second = await asyncio.wait_for(queue.dequeue(), timeout=0.5)

        self.assertEqual(first.request_id, "vip")
        self.assertEqual(second.request_id, "standard")

    async def test_starvation_prevention_ages_items(self):
        queue = Queue(
            QueueConfig(
                max_size=10,
                starvation_prevention=True,
                aging_interval_sec=1,
                default_priority=10,
            )
        )

        await queue.enqueue("old", payload={}, priority=10)
        await asyncio.sleep(1.1)  # Allow item to age and boost its priority
        await queue.enqueue("newer", payload={}, priority=9)

        job = await asyncio.wait_for(queue.dequeue(), timeout=0.5)
        self.assertEqual(job.request_id, "old")

    async def test_queue_full_raises_buffer_error(self):
        queue = Queue(
            QueueConfig(
                max_size=1,
                starvation_prevention=False,
                aging_interval_sec=60,
                default_priority=10,
            )
        )

        await queue.enqueue("first", payload={}, priority=5)
        with self.assertRaises(BufferError):
            await queue.enqueue("second", payload={}, priority=1)

    async def test_dequeue_waits_until_item_available(self):
        queue = Queue(
            QueueConfig(
                max_size=10,
                starvation_prevention=False,
                aging_interval_sec=60,
                default_priority=10,
            )
        )

        dequeue_task = asyncio.create_task(queue.dequeue())
        await asyncio.sleep(0.05)
        self.assertFalse(dequeue_task.done())

        await queue.enqueue("late", payload={}, priority=5)
        job = await asyncio.wait_for(dequeue_task, timeout=0.5)
        self.assertEqual(job.request_id, "late")

    async def test_stats_reports_depth_and_priority_bounds(self):
        queue = Queue(
            QueueConfig(
                max_size=10,
                starvation_prevention=False,
                aging_interval_sec=60,
                default_priority=10,
            )
        )

        await queue.enqueue("alpha", payload={}, priority=5)
        await queue.enqueue("beta", payload={}, priority=2)

        stats = await queue.stats()
        self.assertEqual(stats["depth"], 2)
        self.assertEqual(stats["min_priority"], 2)
        self.assertEqual(stats["max_priority"], 5)
        self.assertGreaterEqual(stats["oldest_wait"], 0.0)
        self.assertEqual(len(queue), 2)


if __name__ == "__main__":
    unittest.main()
