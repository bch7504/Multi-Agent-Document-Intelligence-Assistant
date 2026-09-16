"""Shared behavior for public API schemas."""

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    """Accept Python field names and expose camelCase JSON aliases."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
