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


class S3Storage(StorageBackend):
    """S3 blob storage. The locator `save` returns is a full `s3://bucket/key` URI, so a
    stored `storage_path` stays readable even if the configured bucket/prefix changes
    later (it never reads a bare filesystem path, so existing local-disk rows need migrating
    before switching an existing deployment to S3).

    boto3 is an optional dependency (`uv sync --extra aws`) imported lazily, so the
    default local-disk deployment never needs it. Credentials come from boto3's normal
    chain — on EC2, the instance profile; no keys in env vars or the repo.
    """

    def __init__(
        self, bucket: str, prefix: str = "", region: str | None = None, client=None
    ) -> None:
        if client is None:
            import boto3  # noqa: PLC0415 — optional dependency, see class docstring

            client = boto3.client("s3", region_name=region)
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    @staticmethod
    def _parse(storage_path: str) -> tuple[str, str]:
        if not storage_path.startswith("s3://"):
            raise ValueError(f"not an S3 locator: {storage_path!r}")
        bucket, _, key = storage_path[len("s3://") :].partition("/")
        return bucket, key

    async def save(self, key: str, content: bytes) -> str:
        full_key = self._full_key(key)
        await run_in_threadpool(
            self._client.put_object,
            Bucket=self._bucket,
            Key=full_key,
            Body=content,
            ServerSideEncryption="AES256",
        )
        return f"s3://{self._bucket}/{full_key}"

    async def read(self, storage_path: str) -> bytes:
        bucket, key = self._parse(storage_path)
        response = await run_in_threadpool(self._client.get_object, Bucket=bucket, Key=key)
        return await run_in_threadpool(response["Body"].read)

    async def delete(self, storage_path: str) -> None:
        # S3 delete_object is already idempotent (no error for a missing key).
        bucket, key = self._parse(storage_path)
        await run_in_threadpool(self._client.delete_object, Bucket=bucket, Key=key)


@lru_cache
def get_storage_backend() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            prefix=settings.s3_prefix,
            region=settings.s3_region or None,
        )
    return LocalDiskStorage(settings.upload_dir)
