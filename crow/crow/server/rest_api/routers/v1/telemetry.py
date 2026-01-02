from typing import Optional

from fastapi import APIRouter, Depends

from crow.schemas.provider_trace import ProviderTrace
from crow.server.rest_api.dependencies import HeaderParams, get_headers, get_crow_server
from crow.server.server import SyncServer
from crow.settings import settings

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/{step_id}", response_model=Optional[ProviderTrace], operation_id="retrieve_provider_trace", deprecated=True)
async def retrieve_provider_trace(
    step_id: str,
    server: SyncServer = Depends(get_crow_server),
    headers: HeaderParams = Depends(get_headers),
):
    """
    **DEPRECATED**: Use `GET /steps/{step_id}/trace` instead.

    Retrieve provider trace by step ID.
    """
    provider_trace = None
    if settings.track_provider_trace:
        try:
            provider_trace = await server.telemetry_manager.get_provider_trace_by_step_id_async(
                step_id=step_id, actor=await server.user_manager.get_actor_or_default_async(actor_id=headers.actor_id)
            )
        except:
            pass

    return provider_trace
