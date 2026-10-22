import boto3
import pytest
from moto import mock_aws

from app.core.config import Settings
from app.core.storage import S3Storage

BUCKET = "hybridrag-test-bucket"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-central-1")
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
        )
        yield client


async def test_save_returns_s3_uri_and_read_roundtrips(s3_client):
    storage = S3Storage(BUCKET, prefix="uploads", client=s3_client)
    locator = await storage.save("u1/d1/v1/a.pdf", b"hello")
    assert locator == f"s3://{BUCKET}/uploads/u1/d1/v1/a.pdf"
    assert await storage.read(locator) == b"hello"


async def test_objects_are_encrypted_at_rest(s3_client):
    storage = S3Storage(BUCKET, client=s3_client)
    await storage.save("k", b"x")
    head = s3_client.head_object(Bucket=BUCKET, Key="k")
    assert head["ServerSideEncryption"] == "AES256"


async def test_delete_removes_object_and_is_idempotent(s3_client):
    storage = S3Storage(BUCKET, client=s3_client)
    locator = await storage.save("k", b"x")
    await storage.delete(locator)
    await storage.delete(locator)  # already gone: must not raise
    assert "Contents" not in s3_client.list_objects_v2(Bucket=BUCKET)


async def test_read_rejects_non_s3_locator(s3_client):
    storage = S3Storage(BUCKET, client=s3_client)
    with pytest.raises(ValueError):
        await storage.read("/data/uploads/a.pdf")


def test_s3_backend_requires_bucket():
    with pytest.raises(ValueError, match="S3_BUCKET"):
        Settings(storage_backend="s3", s3_bucket="")
