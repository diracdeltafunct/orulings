from django import forms


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
