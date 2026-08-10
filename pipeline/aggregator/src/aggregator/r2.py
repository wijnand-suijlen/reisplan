"""Optionele upload naar Cloudflare R2 (S3-compatibel).

Actief zodra R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY_ID en R2_SECRET_ACCESS_KEY in de
omgeving (.env) staan; anders doet dit stilletjes niets. Uploads zijn gzip met
Content-Encoding zodat browsers ze transparant uitpakken — scheelt ~85% egress.
"""

import gzip
import logging
import os

log = logging.getLogger("aggregator")
_client = None

_NODIG = ["R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"]


def actief() -> bool:
    return all(os.environ.get(k) for k in _NODIG)


def upload(sleutel: str, data: bytes, content_type: str, cache_s: int = 30) -> None:
    if not actief():
        return
    global _client
    if _client is None:
        # negeer eventuele (kapotte/bedrijfs-)~/.aws-configuratie: wij geven alles expliciet mee
        os.environ.setdefault("AWS_CONFIG_FILE", os.devnull)
        os.environ.setdefault("AWS_SHARED_CREDENTIALS_FILE", os.devnull)
        import boto3

        _client = boto3.client(
            "s3",
            endpoint_url=os.environ["R2_ENDPOINT"],
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )
    _client.put_object(
        Bucket=os.environ["R2_BUCKET"],
        Key=sleutel,
        Body=gzip.compress(data),
        ContentType=content_type,
        ContentEncoding="gzip",
        CacheControl=f"max-age={cache_s}",
    )
