import json
import time
from typing import AsyncIterator, Optional, Union
from uuid import uuid4

from fastapi.responses import StreamingResponse
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta

from crow.agents.agent_loop import AgentLoop
from crow.agents.base_agent_v2 import BaseAgentV2
from crow.constants import REDIS_RUN_ID_PREFIX
from crow.data_sources.redis_client import NoopAsyncRedisClient, get_redis_client
from crow.errors import (
    CrowInvalidArgumentError,
    CrowServiceUnavailableError,
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    PendingApprovalError,
)
from crow.helpers.datetime_helpers import get_utc_timestamp_ns
from crow.log import get_logger
from crow.otel.context import get_ctx_attributes
from crow.otel.metric_registry import MetricRegistry
from crow.schemas.agent import AgentState
from crow.schemas.enums import AgentType, MessageStreamStatus, RunStatus
from crow.schemas.job import CrowRequestConfig
from crow.schemas.crow_message import AssistantMessage, CrowErrorMessage, MessageType
from crow.schemas.crow_message_content import TextContent
from crow.schemas.crow_request import CrowStreamingRequest
from crow.schemas.crow_response import CrowResponse
from crow.schemas.crow_stop_reason import CrowStopReason, StopReasonType
from crow.schemas.message import MessageCreate
from crow.schemas.run import Run as PydanticRun, RunUpdate
from crow.schemas.usage import CrowUsageStatistics
from crow.schemas.user import User
from crow.server.rest_api.redis_stream_manager import create_background_stream_processor, redis_sse_stream_generator
from crow.server.rest_api.streaming_response import (
    StreamingResponseWithStatusCode,
    add_keepalive_to_stream,
    cancellation_aware_stream_wrapper,
)
from crow.server.rest_api.utils import capture_sentry_exception
from crow.services.run_manager import RunManager
from crow.settings import settings
from crow.utils import safe_create_task

logger = get_logger(__name__)


class StreamingService:
    """
    Service for managing agent streaming responses.
    Handles run creation, stream generation, error handling, and format conversion.
    """

    def __init__(self, server):
        """
        Initialize the streaming service.

        Args:
            server: The SyncServer instance for accessing managers and services
        """
        self.server = server
        self.runs_manager = RunManager() if settings.track_agent_run else None

    async def create_agent_stream(
        self,
        agent_id: str,
        actor: User,
        request: CrowStreamingRequest,
        run_type: str = "streaming",
    ) -> tuple[Optional[PydanticRun], Union[StreamingResponse, CrowResponse]]:
        """
        Create a streaming response for an agent.

        Args:
            agent_id: The agent ID to stream from
            actor: The user making the request
            request: The CrowStreamingRequest containing all request parameters
            run_type: Type of run for tracking

        Returns:
            Tuple of (run object or None, streaming response)
        """
        request_start_timestamp_ns = get_utc_timestamp_ns()
        MetricRegistry().user_message_counter.add(1, get_ctx_attributes())

        # get redis client
        redis_client = await get_redis_client()

        # load agent and check eligibility
        agent = await self.server.agent_manager.get_agent_by_id_async(
            agent_id, actor, include_relationships=["memory", "multi_agent_group", "sources", "tool_exec_environment_variables", "tools"]
        )

        agent_eligible = self._is_agent_eligible(agent)
        model_compatible = self._is_model_compatible(agent)
        model_compatible_token_streaming = self._is_token_streaming_compatible(agent)

        # create run if tracking is enabled
        run = None
        run_update_metadata = None
        if settings.track_agent_run:
            run = await self._create_run(agent_id, request, run_type, actor)
            await redis_client.set(f"{REDIS_RUN_ID_PREFIX}:{agent_id}", run.id if run else None)

        try:
            if agent_eligible and model_compatible:
                # use agent loop for streaming
                agent_loop = AgentLoop.load(agent_state=agent, actor=actor)

                # create the base stream with error handling
                raw_stream = self._create_error_aware_stream(
                    agent_loop=agent_loop,
                    messages=request.messages,
                    max_steps=request.max_steps,
                    stream_tokens=request.stream_tokens and model_compatible_token_streaming,
                    run_id=run.id if run else None,
                    use_assistant_message=request.use_assistant_message,
                    request_start_timestamp_ns=request_start_timestamp_ns,
                    include_return_message_types=request.include_return_message_types,
                    actor=actor,
                )

                # handle background streaming if requested
                if request.background and settings.track_agent_run:
                    if isinstance(redis_client, NoopAsyncRedisClient):
                        raise CrowServiceUnavailableError(
                            f"Background streaming requires Redis to be running. "
                            f"Please ensure Redis is properly configured. "
                            f"CROW_REDIS_HOST: {settings.redis_host}, CROW_REDIS_PORT: {settings.redis_port}",
                            service_name="redis",
                        )

                    # Wrap the agent loop stream with cancellation awareness for background task
                    background_stream = raw_stream
                    if settings.enable_cancellation_aware_streaming and run:
                        background_stream = cancellation_aware_stream_wrapper(
                            stream_generator=raw_stream,
                            run_manager=self.runs_manager,
                            run_id=run.id,
                            actor=actor,
                        )

                    safe_create_task(
                        create_background_stream_processor(
                            stream_generator=background_stream,
                            redis_client=redis_client,
                            run_id=run.id,
                            run_manager=self.server.run_manager,
                            actor=actor,
                        ),
                        label=f"background_stream_processor_{run.id}",
                    )

                    raw_stream = redis_sse_stream_generator(
                        redis_client=redis_client,
                        run_id=run.id,
                    )

                # wrap client stream with cancellation awareness if enabled and tracking runs
                stream = raw_stream
                if settings.enable_cancellation_aware_streaming and settings.track_agent_run and run and not request.background:
                    stream = cancellation_aware_stream_wrapper(
                        stream_generator=raw_stream,
                        run_manager=self.runs_manager,
                        run_id=run.id,
                        actor=actor,
                    )

                # conditionally wrap with keepalive based on request parameter
                if request.include_pings and settings.enable_keepalive:
                    stream = add_keepalive_to_stream(stream, keepalive_interval=settings.keepalive_interval, run_id=run.id)

                result = StreamingResponseWithStatusCode(
                    stream,
                    media_type="text/event-stream",
                )
            else:
                # fallback to non-agent-loop streaming
                result = await self.server.send_message_to_agent(
                    agent_id=agent_id,
                    actor=actor,
                    input_messages=request.messages,
                    stream_steps=True,
                    stream_tokens=request.stream_tokens,
                    use_assistant_message=request.use_assistant_message,
                    assistant_message_tool_name=request.assistant_message_tool_name,
                    assistant_message_tool_kwarg=request.assistant_message_tool_kwarg,
                    request_start_timestamp_ns=request_start_timestamp_ns,
                    include_return_message_types=request.include_return_message_types,
                )

            # update run status to running before returning
            if settings.track_agent_run and run:
                run_status = RunStatus.running

            return run, result

        except PendingApprovalError as e:
            if settings.track_agent_run:
                run_update_metadata = {"error": str(e)}
                run_status = RunStatus.failed
            raise
        except Exception as e:
            if settings.track_agent_run:
                run_update_metadata = {"error": str(e)}
                run_status = RunStatus.failed
            raise
        finally:
            if settings.track_agent_run and run:
                await self.server.run_manager.update_run_by_id_async(
                    run_id=run.id,
                    update=RunUpdate(status=run_status, metadata=run_update_metadata),
                    actor=actor,
                )

    async def create_agent_stream_openai_chat_completions(
        self,
        agent_id: str,
        actor: User,
        request: CrowStreamingRequest,
    ) -> StreamingResponse:
        """
        Create OpenAI-compatible chat completions streaming response.

        Transforms Crow's internal streaming format to match OpenAI's
        ChatCompletionChunk schema, filtering out internal tool execution
        and only streaming assistant text responses.

        Args:
            agent_id: The agent ID to stream from
            actor: The user making the request
            request: The CrowStreamingRequest containing all request parameters

        Returns:
            StreamingResponse with OpenAI-formatted SSE chunks
        """
        # load agent to get model info for the completion chunks
        agent = await self.server.agent_manager.get_agent_by_id_async(agent_id, actor)

        # create standard Crow stream (returns SSE-formatted stream)
        run, crow_stream_response = await self.create_agent_stream(
            agent_id=agent_id,
            actor=actor,
            request=request,
            run_type="openai_chat_completions",
        )

        # extract the stream iterator from the response
        if isinstance(crow_stream_response, StreamingResponseWithStatusCode):
            crow_stream = crow_stream_response.body_iterator
        else:
            raise CrowInvalidArgumentError(
                "Agent is not compatible with streaming mode",
                argument_name="model",
            )

        # create transformer with agent's model info
        model_name = agent.llm_config.model if agent.llm_config else "unknown"
        completion_id = f"chatcmpl-{run.id if run else str(uuid4())}"

        transformer = OpenAIChatCompletionsStreamTransformer(
            model=model_name,
            completion_id=completion_id,
        )

        # transform Crow SSE stream to OpenAI format (parser handles SSE strings)
        openai_stream = transformer.transform_stream(crow_stream)

        return StreamingResponse(
            openai_stream,
            media_type="text/event-stream",
        )

    def _create_error_aware_stream(
        self,
        agent_loop: BaseAgentV2,
        messages: list[MessageCreate],
        max_steps: int,
        stream_tokens: bool,
        run_id: Optional[str],
        use_assistant_message: bool,
        request_start_timestamp_ns: int,
        include_return_message_types: Optional[list[MessageType]],
        actor: User,
    ) -> AsyncIterator:
        """
        Create a stream with unified error handling.

        Returns:
            Async iterator that yields chunks with proper error handling
        """

        async def error_aware_stream():
            """Stream that handles early LLM errors gracefully in streaming format."""
            run_status = None
            run_update_metadata = None
            stop_reason = None
            error_data = None
            saw_done = False
            saw_error = False

            try:
                stream = agent_loop.stream(
                    input_messages=messages,
                    max_steps=max_steps,
                    stream_tokens=stream_tokens,
                    run_id=run_id,
                    use_assistant_message=use_assistant_message,
                    request_start_timestamp_ns=request_start_timestamp_ns,
                    include_return_message_types=include_return_message_types,
                )

                async for chunk in stream:
                    # Track terminal events
                    if isinstance(chunk, str):
                        if "data: [DONE]" in chunk:
                            saw_done = True
                        if "event: error" in chunk:
                            saw_error = True
                    yield chunk

                # Stream completed - check if we got a terminal event
                if not saw_done and not saw_error:
                    # Stream ended without terminal - treat as error to avoid hanging clients
                    logger.error(
                        f"Stream for run {run_id} ended without terminal event. "
                        f"Agent stop_reason: {agent_loop.stop_reason}. Emitting error + [DONE]."
                    )
                    stop_reason = CrowStopReason(stop_reason=StopReasonType.error)
                    error_message = CrowErrorMessage(
                        run_id=run_id,
                        error_type="stream_incomplete",
                        message="Stream ended unexpectedly without a terminal event.",
                        detail=None,
                    )
                    error_data = {"error": error_message.model_dump()}
                    yield f"data: {stop_reason.model_dump_json()}\n\n"
                    yield f"event: error\ndata: {error_message.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"
                    saw_error = True
                    saw_done = True
                    run_status = RunStatus.failed

                else:
                    # set run status after successful completion
                    if agent_loop.stop_reason and agent_loop.stop_reason.stop_reason.value == "cancelled":
                        run_status = RunStatus.cancelled
                    else:
                        run_status = RunStatus.completed
                    stop_reason = agent_loop.stop_reason if agent_loop.stop_reason else CrowStopReason(stop_reason=StopReasonType.end_turn)

            except LLMTimeoutError as e:
                run_status = RunStatus.failed
                stop_reason = CrowStopReason(stop_reason=StopReasonType.llm_api_error)
                error_message = CrowErrorMessage(
                    run_id=run_id,
                    error_type="llm_timeout",
                    message="The LLM request timed out. Please try again.",
                    detail=str(e),
                )
                error_data = {"error": error_message.model_dump()}
                logger.error(f"Run {run_id} stopped with LLM timeout error: {e}, error_data: {error_message.model_dump()}")
                yield f"data: {stop_reason.model_dump_json()}\n\n"
                yield f"event: error\ndata: {error_message.model_dump_json()}\n\n"
                # Send [DONE] marker to properly close the stream
                yield "data: [DONE]\n\n"
            except LLMRateLimitError as e:
                run_status = RunStatus.failed
                stop_reason = CrowStopReason(stop_reason=StopReasonType.llm_api_error)
                error_message = CrowErrorMessage(
                    run_id=run_id,
                    error_type="llm_rate_limit",
                    message="Rate limit exceeded for LLM model provider. Please wait before making another request.",
                    detail=str(e),
                )
                error_data = {"error": error_message.model_dump()}
                logger.warning(f"Run {run_id} stopped with LLM rate limit error: {e}, error_data: {error_message.model_dump()}")
                yield f"data: {stop_reason.model_dump_json()}\n\n"
                yield f"event: error\ndata: {error_message.model_dump_json()}\n\n"
                # Send [DONE] marker to properly close the stream
                yield "data: [DONE]\n\n"
            except LLMAuthenticationError as e:
                run_status = RunStatus.failed
                stop_reason = CrowStopReason(stop_reason=StopReasonType.llm_api_error)
                error_message = CrowErrorMessage(
                    run_id=run_id,
                    error_type="llm_authentication",
                    message="Authentication failed with the LLM model provider.",
                    detail=str(e),
                )
                error_data = {"error": error_message.model_dump()}
                logger.warning(f"Run {run_id} stopped with LLM authentication error: {e}, error_data: {error_message.model_dump()}")
                yield f"data: {stop_reason.model_dump_json()}\n\n"
                yield f"event: error\ndata: {error_message.model_dump_json()}\n\n"
                # Send [DONE] marker to properly close the stream
                yield "data: [DONE]\n\n"
            except LLMError as e:
                run_status = RunStatus.failed
                stop_reason = CrowStopReason(stop_reason=StopReasonType.llm_api_error)
                error_message = CrowErrorMessage(
                    run_id=run_id,
                    error_type="llm_error",
                    message="An error occurred with the LLM request.",
                    detail=str(e),
                )
                error_data = {"error": error_message.model_dump()}
                logger.error(f"Run {run_id} stopped with LLM error: {e}, error_data: {error_message.model_dump()}")
                yield f"data: {stop_reason.model_dump_json()}\n\n"
                yield f"event: error\ndata: {error_message.model_dump_json()}\n\n"
                # Send [DONE] marker to properly close the stream
                yield "data: [DONE]\n\n"
            except Exception as e:
                run_status = RunStatus.failed
                stop_reason = CrowStopReason(stop_reason=StopReasonType.error)
                error_message = CrowErrorMessage(
                    run_id=run_id,
                    error_type="internal_error",
                    message="An unknown error occurred with the LLM streaming request.",
                    detail=str(e),
                )
                error_data = {"error": error_message.model_dump()}
                logger.error(f"Run {run_id} stopped with unknown error: {e}, error_data: {error_message.model_dump()}")
                yield f"data: {stop_reason.model_dump_json()}\n\n"
                yield f"event: error\ndata: {error_message.model_dump_json()}\n\n"
                # Send [DONE] marker to properly close the stream
                yield "data: [DONE]\n\n"
                # Capture for Sentry but don't re-raise to allow stream to complete gracefully
                capture_sentry_exception(e)
            finally:
                # always update run status, whether success or failure
                if run_id and self.runs_manager and run_status:
                    # Extract stop_reason enum value from CrowStopReason object
                    stop_reason_value = stop_reason.stop_reason if stop_reason else StopReasonType.error.value
                    await self.runs_manager.update_run_by_id_async(
                        run_id=run_id,
                        update=RunUpdate(status=run_status, stop_reason=stop_reason_value, metadata=error_data),
                        actor=actor,
                    )

        return error_aware_stream()

    def _is_agent_eligible(self, agent: AgentState) -> bool:
        """Check if agent is eligible for streaming."""
        return agent.multi_agent_group is None or agent.multi_agent_group.manager_type in ["sleeptime", "voice_sleeptime"]

    def _is_model_compatible(self, agent: AgentState) -> bool:
        """Check if agent's model is compatible with streaming."""
        return agent.llm_config.model_endpoint_type in [
            "anthropic",
            "openai",
            "together",
            "google_ai",
            "google_vertex",
            "bedrock",
            "ollama",
            "azure",
            "xai",
            "groq",
            "deepseek",
        ]

    def _is_token_streaming_compatible(self, agent: AgentState) -> bool:
        """Check if agent's model supports token-level streaming."""
        base_compatible = agent.llm_config.model_endpoint_type in ["anthropic", "openai", "bedrock", "deepseek"]
        google_crow_v1 = agent.agent_type == AgentType.crow_v1_agent and agent.llm_config.model_endpoint_type in [
            "google_ai",
            "google_vertex",
        ]
        return base_compatible or google_crow_v1

    async def _create_run(self, agent_id: str, request: CrowStreamingRequest, run_type: str, actor: User) -> PydanticRun:
        """Create a run for tracking execution."""
        run = await self.runs_manager.create_run(
            pydantic_run=PydanticRun(
                agent_id=agent_id,
                background=request.background or False,
                metadata={
                    "run_type": run_type,
                },
                request_config=CrowRequestConfig.from_crow_request(request),
            ),
            actor=actor,
        )
        return run

    async def _update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        actor: User,
        error: Optional[str] = None,
        stop_reason: Optional[str] = None,
    ):
        """Update the status of a run."""
        if not self.runs_manager:
            return

        update = RunUpdate(status=status)
        if error:
            update.metadata = {"error": error}
        if stop_reason:
            update.stop_reason = stop_reason

        await self.runs_manager.update_run_by_id_async(
            run_id=run_id,
            update=update,
            actor=actor,
        )


class OpenAIChatCompletionsStreamTransformer:
    """
    Transforms Crow streaming messages into OpenAI ChatCompletionChunk format.
    Filters out internal tool execution and only streams assistant text responses.
    """

    def __init__(self, model: str, completion_id: str):
        """
        Initialize the transformer.

        Args:
            model: Model name to include in chunks
            completion_id: Unique ID for this completion (format: chatcmpl-{uuid})
        """
        self.model = model
        self.completion_id = completion_id
        self.first_chunk = True
        self.created = int(time.time())

    # TODO: This is lowkey really ugly and poor code design, but this works fine for now
    def _parse_sse_chunk(self, sse_string: str):
        """
        Parse SSE-formatted string back into a message object.

        Args:
            sse_string: SSE formatted string like "data: {...}\n\n"

        Returns:
            Parsed message object or None if can't parse
        """
        try:
            # strip SSE formatting
            if sse_string.startswith("data: "):
                json_str = sse_string[6:].strip()

                # handle [DONE] marker
                if json_str == "[DONE]":
                    return MessageStreamStatus.done

                # parse JSON
                data = json.loads(json_str)

                # reconstruct message object based on message_type
                message_type = data.get("message_type")

                if message_type == "assistant_message":
                    return AssistantMessage(**data)
                elif message_type == "usage_statistics":
                    return CrowUsageStatistics(**data)
                elif message_type == "stop_reason":
                    # skip stop_reason, we use [DONE] instead
                    return None
                else:
                    # other message types we skip
                    return None
            return None
        except Exception as e:
            logger.warning(f"Failed to parse SSE chunk: {e}")
            return None

    async def transform_stream(self, crow_stream: AsyncIterator) -> AsyncIterator[str]:
        """
        Transform Crow stream to OpenAI ChatCompletionChunk SSE format.

        Args:
            crow_stream: Async iterator of Crow messages (may be SSE strings or objects)

        Yields:
            SSE-formatted strings: "data: {json}\n\n"
        """
        try:
            async for raw_chunk in crow_stream:
                # parse SSE string if needed
                if isinstance(raw_chunk, str):
                    chunk = self._parse_sse_chunk(raw_chunk)
                    if chunk is None:
                        continue  # skip unparseable or filtered chunks
                else:
                    chunk = raw_chunk

                # only process assistant messages
                if isinstance(chunk, AssistantMessage):
                    async for sse_chunk in self._process_assistant_message(chunk):
                        print(f"CHUNK: {sse_chunk}")
                        yield sse_chunk

                # handle completion status
                elif chunk == MessageStreamStatus.done:
                    # emit final chunk with finish_reason
                    final_chunk = ChatCompletionChunk(
                        id=self.completion_id,
                        object="chat.completion.chunk",
                        created=self.created,
                        model=self.model,
                        choices=[
                            Choice(
                                index=0,
                                delta=ChoiceDelta(),
                                finish_reason="stop",
                            )
                        ],
                    )
                    yield f"data: {final_chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error in OpenAI stream transformation: {e}", exc_info=True)
            error_chunk = {"error": {"message": str(e), "type": "server_error"}}
            yield f"data: {json.dumps(error_chunk)}\n\n"

    async def _process_assistant_message(self, message: AssistantMessage) -> AsyncIterator[str]:
        """
        Convert AssistantMessage to OpenAI ChatCompletionChunk(s).

        Args:
            message: Crow AssistantMessage with content

        Yields:
            SSE-formatted chunk strings
        """
        # extract text from content (can be string or list of TextContent)
        text_content = self._extract_text_content(message.content)
        if not text_content:
            return

        # emit role on first chunk only
        if self.first_chunk:
            self.first_chunk = False
            # first chunk includes role
            chunk = ChatCompletionChunk(
                id=self.completion_id,
                object="chat.completion.chunk",
                created=self.created,
                model=self.model,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(role="assistant", content=text_content),
                        finish_reason=None,
                    )
                ],
            )
        else:
            # subsequent chunks just have content
            chunk = ChatCompletionChunk(
                id=self.completion_id,
                object="chat.completion.chunk",
                created=self.created,
                model=self.model,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(content=text_content),
                        finish_reason=None,
                    )
                ],
            )

        yield f"data: {chunk.model_dump_json()}\n\n"

    def _extract_text_content(self, content: Union[str, list[TextContent]]) -> str:
        """
        Extract text string from content field.

        Args:
            content: Either a string or list of TextContent objects

        Returns:
            Extracted text string
        """
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # concatenate all TextContent items
            text_parts = []
            for item in content:
                if isinstance(item, TextContent):
                    text_parts.append(item.text)
            return "".join(text_parts)
        return ""
