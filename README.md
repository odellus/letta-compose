# letta-compose

I was having trouble with setting up letta and I don't have a clickhouse account so I just was like let's put all of that inside [`compose.yaml`](./compose.yaml)

## Start the local letta server
```bash
cd path/to/letta-compose
# Copy example to .env
cp .env.example .env
# Update to point to your local openai compatible servers
nano .env
# start letta server
docker compose up -d
```

## Create an agent and say hello
```python
from letta_client import Letta

# Create a client to our local letta instance
client = Letta(base_url='http://localhost:8283')

agent = client.agents.create(
    llm_config={
        'model': '/home/thomas-wood/.cache/llama.cpp/unsloth_GLM-4.5-Air-GGUF_Q4_K_M_GLM-4.5-Air-Q4_K_M-00001-of-00002.gguf',
        'model_endpoint': 'http://coast-after-3:1234/v1',
        'model_endpoint_type': 'openai',
        'context_window': 30000,
    },
    embedding='ollama/mxbai-embed-large:latest',
    memory_blocks=[
        {'label': 'persona', 'value': 'I am a helpful assistant.'}
    ]
)
print('Agent created:', agent.id)

# Now let's use it
client = Letta(base_url='http://localhost:8283')

response = client.agents.messages.create(
    agent_id=agent.id,
    messages=[{'role': 'user', 'content': 'Hello, who are you?'}]
)
for msg in response.messages:
    print(type(msg).__name__, ':', getattr(msg, 'content', None) or getattr(msg, 'reasoning', None) or msg)

```
