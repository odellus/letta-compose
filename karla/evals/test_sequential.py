"""Simple sequential test to verify one-at-a-time execution."""
import asyncio
import time

async def test_semaphore():
    """Test that semaphore limits to 1."""
    import anyio
    
    semaphore = anyio.Semaphore(1)
    results = []
    
    async def task(name):
        print(f"[{time.strftime('%H:%M:%S')}] {name}: waiting for semaphore")
        async with semaphore:
            print(f"[{time.strftime('%H:%M:%S')}] {name}: acquired semaphore, working...")
            await asyncio.sleep(2)
            print(f"[{time.strftime('%H:%M:%S')}] {name}: done")
            results.append(name)
    
    async with anyio.create_task_group() as tg:
        for i in range(3):
            tg.start_soon(task, f"task-{i}")
    
    print(f"Results order: {results}")

if __name__ == "__main__":
    asyncio.run(test_semaphore())
