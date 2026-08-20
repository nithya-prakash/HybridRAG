from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings


class StorageBackend(ABC):
    """Blob storage behind two operations. `key` is a relative, caller-chosen,
    caller-sanitized path-like string (e.g. "{user_id}/{document_id}/v{version}/{filename}")
    used only to organize storage on write. `save` returns an opaque, backend-specific
    locator — persist it as `storage_path` and hand it back to `delete` unchanged; never
    reconstruct it from `key` yourself, since a future backend (e.g. S3) may return
    something that isn't a simple base_dir + key join.
    """

    @abstractmethod
    async def save(self, key: str, content: bytes) -> str:
        """Persist `content` under `key` and return a storage_path locator."""

    @abstractmethod
    async def read(self, storage_path: str) -> bytes:
        """Read back the blob at `storage_path` (as returned by `save`)."""

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        """Remove the blob at `storage_path` (as returned by `save`). Must not raise
        if it's already gone."""


class LocalDiskStorage(StorageBackend):
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)

    async def save(self, key: str, content: bytes) -> str:
        path = self._base_dir / key
        await run_in_threadpool(self._write, path, content)
        return str(path)

    async def read(self, storage_path: str) -> bytes:
        return await run_in_threadpool(Path(storage_path).read_bytes)

    async def delete(self, storage_path: str) -> None:
        await run_in_threadpool(self._delete, Path(storage_path))

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    @staticmethod
    def _delete(path: Path) -> None:
        path.unlink(missing_ok=True)


@lru_cache
def get_storage_backend() -> StorageBackend:
    # Local disk is the only backend today. Swapping to S3 later means adding an
    # S3Storage(StorageBackend) implementation and changing this factory — nothing
    # in the service/router layer references LocalDiskStorage directly.
    settings = get_settings()
    return LocalDiskStorage(settings.upload_dir)
