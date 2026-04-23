from django.db import models
import uuid
from django.contrib.auth.models import AbstractUser

# Create your models here.


class User(AbstractUser):
    class UserType(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        EXHIBITOR = "EXHIBITOR", "Exhibitor"

    user_type = models.CharField(max_length=20, choices=UserType.choices)

# ---------------------------
# 1. Event
# ---------------------------
class Event(models.Model):
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    location = models.CharField(max_length=255)

    def __str__(self):
        return self.name
    

# ---------------------------
# 2. Exhibitor (Company / Stall)
# ---------------------------
class Exhibitor(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="exhibitor"
    )
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="exhibitor")
    company_name = models.CharField(max_length=255)
    stand_name = models.CharField(max_length=255, blank=True, null=True)
    contact_person = models.CharField(max_length=255)
    email = models.EmailField()
    pass_limit = models.PositiveIntegerField(default=20)

    def __str__(self):
        return self.company_name    
    
# ---------------------------
# 3. Attendee (Base Model)
# ---------------------------
class Attendee(models.Model):

    class AttendeeType(models.TextChoices):
        EXHIBITOR = "EXHIBITOR", "Exhibitor"
        VISITOR = "VISITOR", "Visitor"
        VIP = "VIP", "VIP"

    class Status(models.TextChoices):
        INVITED = "INVITED", "Invited"
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"

    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="attendees")
    exhibitor = models.ForeignKey(
        "Exhibitor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendees"
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    mobile_number = models.CharField(max_length=20)
    job_title = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255)
    country_of_residence = models.CharField(max_length=100)
    nationality = models.CharField(max_length=100)
    attendee_type = models.CharField(max_length=20, choices=AttendeeType.choices)
    source = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)    
    digital_badge_issued = models.BooleanField(default=False)
    onsite_badge_printed = models.BooleanField(default=False)
    accepted_terms = models.BooleanField(default=False)
    accepted_data_sharing = models.BooleanField(default=False)
    accepted_marketing = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.attendee_type})"


# ---------------------------
# 4. Badge
# ---------------------------
class Badge(models.Model):

    class BadgeType(models.TextChoices):
        EXHIBITOR = "EXHIBITOR", "Exhibitor"
        VISITOR = "VISITOR", "Visitor"
        VIP = "VIP", "VIP"
    ticket_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )
    attendee = models.OneToOneField(Attendee, on_delete=models.CASCADE, related_name="badge")
    badge_type = models.CharField(max_length=20, choices=BadgeType.choices)
    ticket_class = models.CharField(max_length=100, blank=True, null=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.attendee} - {self.badge_type}"