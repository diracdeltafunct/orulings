from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import UserProfile


class BootstrapFormMixin:
    def apply_bootstrap_classes(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class SignUpForm(BootstrapFormMixin, UserCreationForm):
    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    discord_handle = forms.CharField(max_length=100, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "name", "email", "discord_handle")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["name"].strip()
        user.email = self.cleaned_data["email"]
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                discord_handle=self.cleaned_data["discord_handle"].strip(),
            )
        return user


class ProfileForm(BootstrapFormMixin, forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    discord_handle = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        profile, _ = UserProfile.objects.get_or_create(user=user)
        kwargs.setdefault(
            "initial",
            {
                "name": user.first_name,
                "email": user.email,
                "discord_handle": profile.discord_handle,
            },
        )
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self):
        self.user.first_name = self.cleaned_data["name"].strip()
        self.user.email = self.cleaned_data["email"]
        self.user.save(update_fields=["first_name", "email"])
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.discord_handle = self.cleaned_data["discord_handle"].strip()
        profile.save(update_fields=["discord_handle"])
        return self.user


class RoleUpdateForm(forms.Form):
    role = forms.ChoiceField(widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, actor, target, **kwargs):
        self.actor = actor
        self.target = target
        super().__init__(*args, **kwargs)
        choices = [("contributor", "General contributor"), ("staff", "Staff")]
        if actor.is_superuser:
            choices.append(("admin", "Admin"))
        self.fields["role"].choices = choices
        self.fields["role"].initial = self.current_role(target)

    @staticmethod
    def current_role(user):
        if user.is_superuser:
            return "admin"
        if user.is_staff:
            return "staff"
        return "contributor"

    def clean(self):
        cleaned_data = super().clean()
        if not self.actor.is_superuser and self.target == self.actor:
            raise forms.ValidationError("Staff cannot modify their own role.")
        if not self.actor.is_superuser and self.target.is_superuser:
            raise forms.ValidationError("Staff cannot modify an admin's role.")
        if not self.actor.is_superuser and cleaned_data.get("role") == "admin":
            raise forms.ValidationError("Only admins can assign the admin role.")
        return cleaned_data

    def save(self):
        role = self.cleaned_data["role"]
        self.target.is_staff = role in {"staff", "admin"}
        self.target.is_superuser = role == "admin"
        self.target.save(update_fields=["is_staff", "is_superuser"])
        return self.target


class ContactForm(forms.Form):
    CONTACT_TYPE_CHOICES = [
        ("email", "Email"),
        ("discord", "Discord"),
    ]

    REASON_CHOICES = [
        ("bug", "Bug Report"),
        ("edit", "Edit Request"),
        ("help", "Help Request"),
        ("rule", "Rule Request"),
        ("other", "Other"),
    ]

    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Your name"}
        ),
    )

    contact_type = forms.ChoiceField(
        choices=CONTACT_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select", "id": "contact-type"}),
    )

    contact_info = forms.CharField(
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Your email or Discord username",
                "id": "contact-info",
            }
        ),
    )

    reason = forms.ChoiceField(
        choices=REASON_CHOICES, widget=forms.Select(attrs={"class": "form-select"})
    )

    message = forms.CharField(
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 6, "placeholder": "Your message..."}
        )
    )
