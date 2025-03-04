# myapp/context_processors.py
from .models import TextAsset


def global_site_data(request):
    copyright = TextAsset.objects.filter(asset_type='copyright').first()
    default_copyright = '© 2025 Copyright '

    return {
        'copyright_text': copyright.content if copyright else default_copyright
    }
