from django.contrib import admin
from post.models import Post, TextAsset, UserProfile

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'pub_date')
    search_fields = ('title', 'content', 'author__username')

    def save_model(self, request, obj, form, change):
        """Associar o autor ao post ao salvá-lo."""
        if not obj.author:
            obj.author = request.user
        obj.save()

@admin.register(TextAsset)
class TextAssetAdmin(admin.ModelAdmin):
    list_display = ('asset_type', 'content')
    search_fields = ('asset_type', 'content')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "discord_handle", "role")
    search_fields = ("user__username", "user__email", "discord_handle")

    @admin.display(description="Role")
    def role(self, obj):
        return obj.role
