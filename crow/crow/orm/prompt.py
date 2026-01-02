from sqlalchemy.orm import Mapped, mapped_column

from crow.orm.mixins import ProjectMixin
from crow.orm.sqlalchemy_base import SqlalchemyBase
from crow.schemas.prompt import Prompt as PydanticPrompt


class Prompt(SqlalchemyBase, ProjectMixin):
    __pydantic_model__ = PydanticPrompt
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(primary_key=True, doc="Unique passage identifier")
    prompt: Mapped[str] = mapped_column(doc="The string contents of the prompt.")
