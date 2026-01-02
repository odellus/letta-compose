import os
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("crow")
except PackageNotFoundError:
    # Fallback for development installations
    __version__ = "0.16.1"

if os.environ.get("CROW_VERSION"):
    __version__ = os.environ["CROW_VERSION"]

# Import sqlite_functions early to ensure event handlers are registered (only for SQLite)
# This is only needed for the server, not for client usage
try:
    from crow.settings import DatabaseChoice, settings

    if settings.database_engine == DatabaseChoice.SQLITE:
        from crow.orm import sqlite_functions
except ImportError:
    # If sqlite_vec is not installed, it's fine for client usage
    pass

# # imports for easier access
from crow.schemas.agent import AgentState
from crow.schemas.block import Block
from crow.schemas.embedding_config import EmbeddingConfig
from crow.schemas.enums import JobStatus
from crow.schemas.file import FileMetadata
from crow.schemas.job import Job
from crow.schemas.crow_message import CrowMessage, CrowPing
from crow.schemas.crow_stop_reason import CrowStopReason
from crow.schemas.llm_config import LLMConfig
from crow.schemas.memory import ArchivalMemorySummary, BasicBlockMemory, ChatMemory, Memory, RecallMemorySummary
from crow.schemas.message import Message
from crow.schemas.organization import Organization
from crow.schemas.passage import Passage
from crow.schemas.source import Source
from crow.schemas.tool import Tool
from crow.schemas.usage import CrowUsageStatistics
from crow.schemas.user import User
