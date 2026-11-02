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


def zmensit_fotku(soubor, max_strana=2000, kvalita=80):
    """Zmensi fotku z telefonu pred ulozenim na R2.

    Delsi strana 2000 px a kvalita 80 stahnou 3 MB fotku zhruba na 200 kB
    a cisla na displeji meridla zustanou citelna. Vystup je vzdy JPEG
    otoceny podle EXIF, ostatni EXIF (vcetne polohy) se zahodi.

    Co Pillow neprecte (napr. HEIC), nebo co by zmenseni nezmensilo,
    se ulozi beze zmeny - fotka odectu se nesmi ztratit. Daniel 2026-11-02."""
    from io import BytesIO
    from pathlib import Path

    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps, UnidentifiedImageError

    vystup = BytesIO()
    try:
        soubor.seek(0)
        with Image.open(soubor) as obrazek:
            upraveny = ImageOps.exif_transpose(obrazek).convert("RGB")
            upraveny.thumbnail((max_strana, max_strana))
            upraveny.save(vystup, "JPEG", quality=kvalita, optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        soubor.seek(0)
        return soubor
    if vystup.tell() >= soubor.size:
        soubor.seek(0)
        return soubor
    return ContentFile(vystup.getvalue(), name=Path(soubor.name).stem + ".jpg")
