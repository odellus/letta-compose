from typing import Literal

from pydantic import Field

from crow.constants import DEFAULT_EMBEDDING_CHUNK_SIZE, CROW_MODEL_ENDPOINT
from crow.schemas.embedding_config import EmbeddingConfig
from crow.schemas.enums import ProviderCategory, ProviderType
from crow.schemas.llm_config import LLMConfig
from crow.schemas.providers.base import Provider


class CrowProvider(Provider):
    provider_type: Literal[ProviderType.crow] = Field(ProviderType.crow, description="The type of the provider.")
    provider_category: ProviderCategory = Field(ProviderCategory.base, description="The category of the provider (base or byok)")

    async def list_llm_models_async(self) -> list[LLMConfig]:
        return [
            LLMConfig(
                model="crow-free",  # NOTE: renamed
                model_endpoint_type="openai",
                model_endpoint=CROW_MODEL_ENDPOINT,
                context_window=30000,
                handle=self.get_handle("crow-free"),
                max_tokens=self.get_default_max_output_tokens("crow-free"),
                provider_name=self.name,
                provider_category=self.provider_category,
            )
        ]

    async def list_embedding_models_async(self):
        return [
            EmbeddingConfig(
                embedding_model="crow-free",  # NOTE: renamed
                embedding_endpoint_type="openai",
                embedding_endpoint="https://embeddings.crow.com/",
                embedding_dim=1536,
                embedding_chunk_size=DEFAULT_EMBEDDING_CHUNK_SIZE,
                handle=self.get_handle("crow-free", is_embedding=True),
            )
        ]
