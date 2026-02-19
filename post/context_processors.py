from .models import TextAsset


def global_site_data(request):
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    default_copyright = "© 2025 Copyright "

    return {
        "copyright_text": copyright_asset.content
        if copyright_asset
        else default_copyright,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
    }
