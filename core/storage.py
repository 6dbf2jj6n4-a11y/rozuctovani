"""
Ukladiste pro foto odectu na Cloudflare R2 (S3-kompatibilni API).
Konfigurace pres env promenne na Railway:
  R2_BUCKET_NAME, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY

Lokalne (bez techto promennych) trida existuje, ale zadny skutecny
upload/cteni fotek se v lokalnim vyvoji zatim nezkousi - staci, ze
import a `manage.py check`/migrace nespadnou.
"""
import os

from storages.backends.s3boto3 import S3Boto3Storage


class R2MediaStorage(S3Boto3Storage):
    bucket_name = os.environ.get("R2_BUCKET_NAME", "")
    endpoint_url = os.environ.get("R2_ENDPOINT_URL", "")
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    region_name = "auto"
    file_overwrite = False
    default_acl = None
    querystring_auth = True
    querystring_expire = 3600
    addressing_style = "virtual"
