from typing import Optional, Union

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel, Field

from crow.errors import CrowInvalidArgumentError
from crow.log import get_logger
from crow.schemas.enums import MessageRole
from crow.schemas.crow_request import CrowStreamingRequest
from crow.schemas.message import MessageCreate
from crow.server.rest_api.dependencies import HeaderParams, get_headers, get_crow_server
from crow.server.server import SyncServer
from crow.services.streaming_service import StreamingService

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request - exactly matching OpenAI's schema."""

    model: str = Field(..., description="ID of the model to use")
    messages: list[ChatCompletionMessageParam] = Field(..., description="Messages comprising the conversation so far")

    # optional parameters
    temperature: Optional[float] = Field(None, ge=0, le=2, description="Sampling temperature")
    top_p: Optional[float] = Field(None, ge=0, le=1, description="Nucleus sampling parameter")
    n: Optional[int] = Field(1, ge=1, description="Number of chat completion choices to generate")
    stream: Optional[bool] = Field(False, description="Whether to stream back partial progress")
    stop: Optional[Union[str, list[str]]] = Field(None, description="Sequences where the API will stop generating")
    max_tokens: Optional[int] = Field(None, description="Maximum number of tokens to generate")
    presence_penalty: Optional[float] = Field(None, ge=-2, le=2, description="Presence penalty")
    frequency_penalty: Optional[float] = Field(None, ge=-2, le=2, description="Frequency penalty")
    user: Optional[str] = Field(None, description="A unique identifier representing your end-user")


async def _handle_chat_completion(
    request: ChatCompletionRequest,
    server: SyncServer,
    headers: HeaderParams,
) -> Union[ChatCompletion, StreamingResponse]:
    """
    Internal handler for chat completion logic.

    Args:
        request: OpenAI-compatible chat completion request
        server: Crow server instance
        headers: Request headers with user info

    Returns:
        Streaming or non-streaming chat completion response
    """
    if request.user:
        actor = await server.user_manager.get_actor_or_default_async(actor_id=request.user)
    else:
        actor = await server.user_manager.get_actor_or_default_async(actor_id=headers.actor_id)

    resolved_agent_id = request.model
    if not resolved_agent_id.startswith("agent-"):
        raise CrowInvalidArgumentError(
            f"For this endpoint, the 'model' field should contain an agent ID (format: 'agent-...'). Received: '{resolved_agent_id}'",
            argument_name="model",
        )
    await server.agent_manager.validate_agent_exists_async(resolved_agent_id, actor)

    # convert OpenAI messages to Crow MessageCreate format
    # NOTE: we only process the last user message
    if len(request.messages) > 1:
        logger.warning(
            f"Chat completions endpoint received {len(request.messages)} messages. "
            "Crow maintains conversation state internally, so only the last user message will be processed. "
            "Previous messages are already stored in the agent's memory."
        )

    last_user_message = None
    for msg in reversed(request.messages):
        role = msg.get("role", "user")
        if role == "user":
            last_user_message = msg
            break

    if not last_user_message:
        raise CrowInvalidArgumentError(
            "No user message found in the request. Please include at least one message with role='user'.",
            argument_name="messages",
        )

    crow_messages = [
        MessageCreate(
            role=MessageRole.user,
            content=last_user_message.get("content", ""),
        )
    ]

    crow_request = CrowStreamingRequest(
        messages=crow_messages,
        stream_tokens=True,
    )

    if request.stream:
        streaming_service = StreamingService(server)
        return await streaming_service.create_agent_stream_openai_chat_completions(
            agent_id=resolved_agent_id,
            actor=actor,
            request=crow_request,
        )
    else:
        raise CrowInvalidArgumentError(
            "Non-streaming chat completions not yet implemented. Please set stream=true.",
            argument_name="stream",
        )


@router.post(
    "/chat/completions",
    response_model=ChatCompletion,
    responses={
        200: {
            "description": "Successful response",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/ChatCompletion"}},
                "text/event-stream": {"description": "Server-Sent Events stream (when stream=true)"},
            },
        }
    },
    operation_id="create_chat_completion",
)
async def create_chat_completion(
    request: ChatCompletionRequest = Body(...),
    server: SyncServer = Depends(get_crow_server),
    headers: HeaderParams = Depends(get_headers),
) -> Union[ChatCompletion, StreamingResponse]:
    """
    Create a chat completion using a Crow agent (OpenAI-compatible).

    This endpoint provides full OpenAI API compatibility. The agent is selected based on:
    - The 'model' parameter in the request (should contain an agent ID in format 'agent-...')

    When streaming is enabled (stream=true), the response will be Server-Sent Events
    with ChatCompletionChunk objects.
    """
    return await _handle_chat_completion(request, server, headers)
