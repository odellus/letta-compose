from enum import Enum
from typing import List, Optional, Union

from pydantic import Field

from crow.schemas.enums import PrimitiveType
from crow.schemas.crow_base import CrowBase


class IdentityType(str, Enum):
    """
    Enum to represent the type of the identity.
    """

    org = "org"
    user = "user"
    other = "other"


class IdentityPropertyType(str, Enum):
    """
    Enum to represent the type of the identity property.
    """

    string = "string"
    number = "number"
    boolean = "boolean"
    json = "json"


class IdentityBase(CrowBase):
    __id_prefix__ = PrimitiveType.IDENTITY.value


class IdentityProperty(CrowBase):
    """A property of an identity"""

    key: str = Field(..., description="The key of the property")
    value: Union[str, int, float, bool, dict] = Field(..., description="The value of the property")
    type: IdentityPropertyType = Field(..., description="The type of the property")


class Identity(IdentityBase):
    id: str = IdentityBase.generate_id_field()
    identifier_key: str = Field(..., description="External, user-generated identifier key of the identity.")
    name: str = Field(..., description="The name of the identity.")
    identity_type: IdentityType = Field(..., description="The type of the identity.")
    project_id: Optional[str] = Field(None, description="The project id of the identity, if applicable.")
    agent_ids: List[str] = Field(..., description="The IDs of the agents associated with the identity.", deprecated=True)
    block_ids: List[str] = Field(..., description="The IDs of the blocks associated with the identity.", deprecated=True)
    organization_id: Optional[str] = Field(None, description="The organization id of the user")
    properties: List[IdentityProperty] = Field(default_factory=list, description="List of properties associated with the identity")


class IdentityCreate(CrowBase):
    identifier_key: str = Field(..., description="External, user-generated identifier key of the identity.")
    name: str = Field(..., description="The name of the identity.")
    identity_type: IdentityType = Field(..., description="The type of the identity.")
    project_id: Optional[str] = Field(None, description="The project id of the identity, if applicable.")
    agent_ids: Optional[List[str]] = Field(None, description="The agent ids that are associated with the identity.", deprecated=True)
    block_ids: Optional[List[str]] = Field(None, description="The IDs of the blocks associated with the identity.", deprecated=True)
    properties: Optional[List[IdentityProperty]] = Field(None, description="List of properties associated with the identity.")


class IdentityUpsert(CrowBase):
    identifier_key: str = Field(..., description="External, user-generated identifier key of the identity.")
    name: str = Field(..., description="The name of the identity.")
    identity_type: IdentityType = Field(..., description="The type of the identity.")
    project_id: Optional[str] = Field(None, description="The project id of the identity, if applicable.")
    agent_ids: Optional[List[str]] = Field(None, description="The agent ids that are associated with the identity.", deprecated=True)
    block_ids: Optional[List[str]] = Field(None, description="The IDs of the blocks associated with the identity.", deprecated=True)
    properties: Optional[List[IdentityProperty]] = Field(None, description="List of properties associated with the identity.")


class IdentityUpdate(CrowBase):
    identifier_key: Optional[str] = Field(None, description="External, user-generated identifier key of the identity.")
    name: Optional[str] = Field(None, description="The name of the identity.")
    identity_type: Optional[IdentityType] = Field(None, description="The type of the identity.")
    agent_ids: Optional[List[str]] = Field(None, description="The agent ids that are associated with the identity.", deprecated=True)
    block_ids: Optional[List[str]] = Field(None, description="The IDs of the blocks associated with the identity.", deprecated=True)
    properties: Optional[List[IdentityProperty]] = Field(None, description="List of properties associated with the identity.")


class PaginatedIdentities(CrowBase):
    """Paginated response for identities"""

    data: List[Identity] = Field(..., description="List of identities")
    next_cursor: Optional[str] = Field(None, description="Cursor for fetching the next page")
    has_more: bool = Field(..., description="Whether more results exist after this page")
