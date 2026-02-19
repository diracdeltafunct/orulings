from django.core.cache import cache

from .models import TextAsset

CACHE_TTL = 60 * 10  # 10 minutes


def global_site_data(request):
    data = cache.get("global_site_data")
    if data is not None:
        return data

    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    default_copyright = "© 2025 Copyright "

    data = {
        "copyright_text": copyright_asset.content
        if copyright_asset
        else default_copyright,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
    }
    cache.set("global_site_data", data, CACHE_TTL)
    return data
