from pydantic import BaseModel, Field, field_validator, ConfigDict


class ApiKeyInSchema(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    base_url: str = Field(min_length=9, max_length=512)
    api_key: str = Field(min_length=1, max_length=256)
    model_name: str = Field(min_length=1, max_length=128)

    @field_validator("provider", "api_key", "model_name")
    @classmethod
    def strip_and_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("不能为空白")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("base_url 必须以 https:// 开头")
        return v


class ApiKeyOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider: str
    base_url: str
    key_suffix: str
    status: str
    model_name: str
    is_default: bool


class EmbeddingKeyInSchema(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    base_url: str = Field(min_length=9, max_length=512)
    api_key: str = Field(min_length=1, max_length=256)
    model_name: str = Field(min_length=1, max_length=128)

    @field_validator("provider", "api_key", "model_name")
    @classmethod
    def strip_and_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("不能为空白")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("base_url 必须以 https:// 开头")
        return v


class EmbeddingKeyOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider: str
    base_url: str
    key_suffix: str
    status: str
    model_name: str
    is_default: bool
