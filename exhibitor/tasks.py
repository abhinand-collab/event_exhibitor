from celery import shared_task
from django.db import transaction,IntegrityError
from .models import Attendee, Badge, Exhibitor
from django.core.mail import send_mail



@shared_task
def bulk_upload_save_task(preview_data, exhibitor_id):
    from .models import Exhibitor  # import inside task (safe)

    exhibitor = Exhibitor.objects.get(id=exhibitor_id)
    event = exhibitor.event

    already_used = Badge.objects.filter(attendee__exhibitor=exhibitor).count()

    valid_rows = []
    skipped = 0

    for row in preview_data:
        if row.get("status") == "valid":
            valid_rows.append(row)
        else:
            skipped += 1

    created = 0
    seen_emails = set()

    with transaction.atomic():
        for row in valid_rows:
            email = row["email"].strip().lower()

            if email in seen_emails:
                skipped += 1
                continue
            seen_emails.add(email)

            if already_used + created >= exhibitor.pass_limit:
                skipped += 1
                continue

            try:
                attendee = Attendee.objects.create(
                    event=event,
                    exhibitor=exhibitor,
                    first_name=row["first_name"],
                    last_name=row.get("last_name", ""),
                    email=email,
                    mobile_number=row.get("mobile_number"),
                    job_title=row.get("job_title"),
                    company_name=row.get("company_name"),
                    country_of_residence=row.get("country"),
                    nationality=row.get("nationality"),
                    attendee_type=row["ticket_type"].upper(),
                    source="Bulk Upload",
                    status="PENDING",
                    accepted_terms=row.get("accepted_terms", False),
                    accepted_data_sharing=row.get("accepted_data_sharing", False),
                    accepted_marketing=row.get("accepted_marketing", False),
                    digital_badge_issued=row.get("digital_badge_issued", False),
                    onsite_badge_printed=row.get("onsite_badge_printed", False),
                )

                Badge.objects.create(
                    attendee=attendee,
                    badge_type=row["ticket_type"].upper(),
                    ticket_class=f"{row['ticket_type']} Pass",
                )

                created += 1

            except IntegrityError:
                skipped += 1

            except Exception:
                skipped += 1

    return {
        "created": created,
        "skipped": skipped,
        "total_valid": len(valid_rows),
    }

@shared_task
def send_invite_email(email, token):
    link = f"http://127.0.0.1:8000/register/{token}/"

    send_mail(
        subject="You're Invited!",
        message=f"Click to register: {link}",
        from_email="abhinand@veuz.in",
        recipient_list=[email],
    )