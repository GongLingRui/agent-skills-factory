"""MinIO / S3 async client wrapper."""

from __future__ import annotations

import io

from minio import Minio

from agent_factory.config import Settings


class MinioClient:
    """Thin wrapper around Minio SDK for common operations."""

    def __init__(self, settings: Settings) -> None:
        self._client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
        self._bucket = settings.MINIO_BUCKET

    async def put_object(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> None:
        self._client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=io.BytesIO(data),
            length=length,
            content_type=content_type,
        )

    async def get_object(self, bucket: str, object_name: str) -> bytes:
        response = self._client.get_object(bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
