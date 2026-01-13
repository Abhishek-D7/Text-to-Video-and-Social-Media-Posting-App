# core/pydantic_base.py
from pydantic import BaseModel

class OrmBase(BaseModel):
    """Base class for Pydantic models with ORM compatibility"""
    model_config = {
        "from_attributes": True,
        "arbitrary_types_allowed": True,
    }