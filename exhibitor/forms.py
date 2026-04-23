from django import forms
from .models import Attendee

COUNTRY_CHOICES = [
    ("", "Select Country"),
    ("ae", "United Arab Emirates"),
    ("sa", "Saudi Arabia"),
    ("kw", "Kuwait"),
    ("qa", "Qatar"),
    ("bh", "Bahrain"),
    ("om", "Oman"),
    ("in", "India"),
    ("pk", "Pakistan"),
    ("gb", "United Kingdom"),
    ("us", "United States"),
    ("eg", "Egypt"),
    ("jo", "Jordan"),
    ("lb", "Lebanon"),
    ("sy", "Syria"),
    ("iq", "Iraq"),
    ("ye", "Yemen"),
    ("ly", "Libya"),
    ("tn", "Tunisia"),
    ("ma", "Morocco"),
    ("dz", "Algeria"),
    ("sd", "Sudan"),
    ("bd", "Bangladesh"),
    ("lk", "Sri Lanka"),
    ("np", "Nepal"),
    ("ph", "Philippines"),
    ("id", "Indonesia"),
    ("my", "Malaysia"),
    ("cn", "China"),
    ("jp", "Japan"),
    ("kr", "South Korea"),
    ("de", "Germany"),
    ("fr", "France"),
    ("it", "Italy"),
    ("es", "Spain"),
    ("nl", "Netherlands"),
    ("be", "Belgium"),
    ("ch", "Switzerland"),
    ("at", "Austria"),
    ("au", "Australia"),
    ("nz", "New Zealand"),
    ("ca", "Canada"),
    ("br", "Brazil"),
    ("za", "South Africa"),
    ("ng", "Nigeria"),
    ("ke", "Kenya"),
]

NATIONALITY_CHOICES = [
    ("", "Select Nationality"),
    ("ae", "Emirati"),
    ("sa", "Saudi"),
    ("kw", "Kuwaiti"),
    ("qa", "Qatari"),
    ("bh", "Bahraini"),
    ("om", "Omani"),
    ("in", "Indian"),
    ("pk", "Pakistani"),
    ("gb", "British"),
    ("us", "American"),
    ("eg", "Egyptian"),
    ("jo", "Jordanian"),
    ("lb", "Lebanese"),
    ("sy", "Syrian"),
    ("iq", "Iraqi"),
    ("ye", "Yemeni"),
    ("ly", "Libyan"),
    ("tn", "Tunisian"),
    ("ma", "Moroccan"),
    ("dz", "Algerian"),
    ("sd", "Sudanese"),
    ("bd", "Bangladeshi"),
    ("lk", "Sri Lankan"),
    ("np", "Nepali"),
    ("ph", "Filipino"),
    ("id", "Indonesian"),
    ("my", "Malaysian"),
    ("cn", "Chinese"),
    ("jp", "Japanese"),
    ("kr", "Korean"),
    ("de", "German"),
    ("fr", "French"),
    ("it", "Italian"),
    ("es", "Spanish"),
    ("nl", "Dutch"),
    ("be", "Belgian"),
    ("ch", "Swiss"),
    ("at", "Austrian"),
    ("au", "Australian"),
    ("nz", "New Zealander"),
    ("ca", "Canadian"),
    ("br", "Brazilian"),
    ("za", "South African"),
    ("ng", "Nigerian"),
    ("ke", "Kenyan"),
]

TICKET_TYPE_CHOICES = [
    ("", "Select Ticket Type"),
    ("VIP", "VIP Pass"),
    ("EXHIBITOR", "Exhibitor Pass"),
    ("VISITOR", "Visitor Pass"),
]


class CreateBadgeForm(forms.Form):
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your firstname",
            "class": "form-control",
            "id": "firstName",
        }),
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your lastname",
            "class": "form-control",
            "id": "lastName",
        }),
    )
    job_title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your job title",
            "class": "form-control",
            "id": "jobTitle",
        }),
    )
    company_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your company name",
            "class": "form-control",
            "id": "companyName",
        }),
    )
    country_of_residence = forms.ChoiceField(
        choices=COUNTRY_CHOICES,
        widget=forms.Select(attrs={
            "class": "form-select select2-modal",
            "id": "countryResidence",
        }),
    )
    nationality = forms.ChoiceField(
        choices=NATIONALITY_CHOICES,
        widget=forms.Select(attrs={
            "class": "form-select select2-modal",
            "id": "nationality",
        }),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "placeholder": "Enter email",
            "class": "form-control",
            "id": "email",
            "style": "height: 42px;",
        }),
    )
    mobile_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            "type": "tel",
            "placeholder": "Enter mobile number",
            "class": "form-control",
            "id": "mobileNumber",
        }),
    )
    ticket_type = forms.ChoiceField(
        choices=TICKET_TYPE_CHOICES,
        widget=forms.Select(attrs={
            "class": "form-select select2-modal",
            "id": "ticketType",
        }),
    )
    accepted_terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "consent1"}),
        error_messages={"required": "You must agree to the Terms & Conditions."},
    )
    accepted_data_sharing = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "consent2"}),
        error_messages={"required": "You must acknowledge the data sharing notice."},
    )
    accepted_marketing = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "consent3"}),
    )

    def clean_first_name(self):
        value = self.cleaned_data.get("first_name", "").strip()
        if len(value) < 2:
            raise forms.ValidationError("First name must be at least 2 characters.")
        if not all(c.isalpha() or c in " -'." for c in value):
            raise forms.ValidationError("First name should only contain letters.")
        return value

    def clean_last_name(self):
        value = self.cleaned_data.get("last_name", "").strip()
        if len(value) < 2:
            raise forms.ValidationError("Last name must be at least 2 characters.")
        if not all(c.isalpha() or c in " -'." for c in value):
            raise forms.ValidationError("Last name should only contain letters.")
        return value

    def clean_country_of_residence(self):
        value = self.cleaned_data.get("country_of_residence")
        if not value:
            raise forms.ValidationError("Please select your country of residence.")
        return value

    def clean_nationality(self):
        value = self.cleaned_data.get("nationality")
        if not value:
            raise forms.ValidationError("Please select your nationality.")
        return value

    def clean_ticket_type(self):
        value = self.cleaned_data.get("ticket_type")
        if not value:
            raise forms.ValidationError("Please select a ticket type.")
        return value