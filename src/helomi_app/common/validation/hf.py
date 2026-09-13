from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download
from huggingface_hub.errors import (
    HFValidationError,
    LocalEntryNotFoundError,
    RepositoryNotFoundError,
)
from huggingface_hub.utils import disable_progress_bars
from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError


class HFModel(BaseModel):
    id: str = Field()
    name: str = Field()
    namespace: str | None = None
    path: Path

    def __init__(self, model_id: str | None = None, **data: Any) -> None:
        if model_id is not None and not data:
            super().__init__(id=model_id)
        else:
            super().__init__(**data)

    def __str__(self) -> str:
        return self.id

    @model_validator(mode="before")
    @classmethod
    def validate_and_resolve(cls, data: Any) -> Any:
        if isinstance(data, cls):
            return data

        if isinstance(data, str):
            repo_id = data
        elif isinstance(data, dict) and "id" in data:
            repo_id = data["id"]
        else:
            raise ValueError(
                "Expected a valid Hugging Face repository ID (str) "
                "or a dictionary with an 'id' key."
            )

        try:
            with disable_progress_bars():
                local_path = snapshot_download(repo_id=repo_id, local_files_only=True)

                if "/" in repo_id:
                    namespace, name = repo_id.split("/", 1)
                else:
                    namespace, name = None, repo_id

                return {
                    "id": repo_id,
                    "name": name,
                    "namespace": namespace,
                    "path": Path(local_path),
                }
        except LocalEntryNotFoundError:
            raise PydanticCustomError(
                "hf_model_not_found",
                "Hugging Face model was not found in the local cache",
            ) from None
        except (RepositoryNotFoundError, HFValidationError) as err:
            raise ValueError(
                f"Invalid Hugging Face model ID '{repo_id}': {err}"
            ) from err
        except Exception as err:
            raise ValueError(
                f"Failed to resolve local Hugging Face model '{repo_id}': {err}"
            ) from err
