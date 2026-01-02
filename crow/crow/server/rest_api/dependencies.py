from typing import TYPE_CHECKING, Optional

from fastapi import Header
from pydantic import BaseModel

if TYPE_CHECKING:
    from crow.server.server import SyncServer


class ExperimentalParams(BaseModel):
    """Experimental parameters used across REST API endpoints."""

    message_async: Optional[bool] = None
    crow_v1_agent: Optional[bool] = None
    crow_v1_agent_message_async: Optional[bool] = None
    modal_sandbox: Optional[bool] = None


class HeaderParams(BaseModel):
    """Common header parameters used across REST API endpoints."""

    actor_id: Optional[str] = None
    user_agent: Optional[str] = None
    project_id: Optional[str] = None
    crow_source: Optional[str] = None
    sdk_version: Optional[str] = None
    experimental_params: Optional[ExperimentalParams] = None


def get_headers(
    actor_id: Optional[str] = Header(None, alias="user_id"),
    user_agent: Optional[str] = Header(None, alias="User-Agent"),
    project_id: Optional[str] = Header(None, alias="X-Project-Id"),
    crow_source: Optional[str] = Header(None, alias="X-Crow-Source"),
    sdk_version: Optional[str] = Header(None, alias="X-Stainless-Package-Version"),
    message_async: Optional[str] = Header(None, alias="X-Experimental-Message-Async"),
    crow_v1_agent: Optional[str] = Header(None, alias="X-Experimental-Crow-V1-Agent"),
    crow_v1_agent_message_async: Optional[str] = Header(None, alias="X-Experimental-Crow-V1-Agent-Message-Async"),
    modal_sandbox: Optional[str] = Header(None, alias="X-Experimental-Modal-Sandbox"),
) -> HeaderParams:
    """Dependency injection function to extract common headers from requests."""
    return HeaderParams(
        actor_id=actor_id,
        user_agent=user_agent,
        project_id=project_id,
        crow_source=crow_source,
        sdk_version=sdk_version,
        experimental_params=ExperimentalParams(
            message_async=(message_async == "true") if message_async else None,
            crow_v1_agent=(crow_v1_agent == "true") if crow_v1_agent else None,
            crow_v1_agent_message_async=(crow_v1_agent_message_async == "true") if crow_v1_agent_message_async else None,
            modal_sandbox=(modal_sandbox == "true") if modal_sandbox else None,
        ),
    )


# TODO: why does this double up the interface?
async def get_crow_server() -> "SyncServer":
    # Check if a global server is already instantiated
    from crow.server.rest_api.app import server

    # assert isinstance(server, SyncServer)
    return server
