```bash
docker run \
  -v ~/.letta/.persist/pgdata:/var/lib/postgresql/data \
  -p 8283:8283 \
  --network host \
  --env-file .env \
  letta/letta:latest
```



```python
from letta_client import Letta

client = Letta(base_url='http://localhost:8283')

response = client.agents.messages.create(
    agent_id='agent-d93e0978-c442-4425-ba5d-a4bf3c4096e5',
    messages=[{'role': 'user', 'content': 'Hello, who are you?'}]
)
for msg in response.messages:
    print(type(msg).__name__, ':', getattr(msg, 'content', None) or getattr(msg, 'reasoning', None) or msg)

```
