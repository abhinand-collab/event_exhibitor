from celery import shared_task
from django.db import transaction,IntegrityError
from .models import Attendee, Badge, Exhibitor
from django.core.mail import send_mail
import logging

logger = logging.getLogger(__name__)

@shared_task
def bulk_upload_save_task(rows, exhibitor_id):
    import re
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    from .models import Exhibitor

    exhibitor = Exhibitor.objects.get(id=exhibitor_id)
    event     = exhibitor.event

    already_used = Badge.objects.filter(attendee__exhibitor=exhibitor).count()

    created     = 0
    skipped     = 0
    seen_emails = set()

    VALID_TICKET_TYPES = {"VIP", "EXHIBITOR", "VISITOR"}
    NAME_RE            = re.compile(r"^[A-Za-z \-'.]+$")
    BATCH_SIZE         = 200

    # Pull existing DB emails once — cheaper than per-row DB hit
    existing_emails = set(
        Attendee.objects.filter(exhibitor=exhibitor)
        .values_list("email", flat=True)
    )

    def is_valid_row(row, email):
        """
        Returns (is_valid, reason_string).
        Mirrors CreateBadgeForm + JS validateRowData rules exactly.
        """
        first_name  = str(row.get("first_name") or "").strip()
        last_name   = str(row.get("last_name")  or "").strip()
        country     = str(row.get("country")     or "").strip()
        nationality = str(row.get("nationality") or "").strip()
        ticket_type = str(row.get("ticket_type") or "").strip().upper()
        accepted_terms = row.get("accepted_terms", False)

        # first_name
        if not first_name:
            return False, "First name is required"
        if len(first_name) < 2:
            return False, "First name must be at least 2 characters"
        if not NAME_RE.match(first_name):
            return False, "First name contains invalid characters"

        # last_name (optional — only validated when present)
        if last_name:
            if len(last_name) < 2:
                return False, "Last name must be at least 2 characters"
            if not NAME_RE.match(last_name):
                return False, "Last name contains invalid characters"

        # email
        if not email or "@" not in email:
            return False, "Invalid email address"
        try:
            validate_email(email)
        except ValidationError:
            return False, "Email address format is invalid"
        if email in existing_emails:
            return False, "Email already exists in database"
        if email in seen_emails:
            return False, "Duplicate email within this upload"

        # country & nationality
        if not country:
            return False, "Country is required"
        if not nationality:
            return False, "Nationality is required"

        # ticket_type
        if not ticket_type:
            return False, "Ticket type is required"
        if ticket_type not in VALID_TICKET_TYPES:
            return False, f"Invalid ticket type: {ticket_type}"

        # terms
        if not accepted_terms:
            return False, "Terms & Conditions must be accepted"

        return True, None

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]

        with transaction.atomic():
            for row in batch:
                raw_email = row.get("email") or ""
                email     = raw_email.strip().lower()

                # Pass limit guard
                if already_used + created >= exhibitor.pass_limit:
                    skipped += 1
                    logger.warning(f"Pass limit reached at {exhibitor.pass_limit}. Skipping {email}.")
                    continue

                # Validate row
                valid, reason = is_valid_row(row, email)
                if not valid:
                    skipped += 1
                    logger.warning(f"Row skipped — {reason} | email={email} | row={row}")
                    continue

                # Safe to add to seen_emails only after passing validation
                seen_emails.add(email)

                try:
                    attendee = Attendee.objects.create(
                        event                = event,
                        exhibitor            = exhibitor,
                        first_name           = str(row.get("first_name") or "").strip(),
                        last_name            = str(row.get("last_name")  or "").strip(),
                        email                = email,
                        mobile_number        = row.get("mobile_number") or None,
                        job_title            = row.get("job_title")     or None,
                        company_name         = row.get("company_name")  or None,
                        country_of_residence = str(row.get("country")     or "").strip(),
                        nationality          = str(row.get("nationality") or "").strip(),
                        attendee_type        = str(row.get("ticket_type") or "").strip().upper(),
                        source               = "Bulk Upload",
                        status               = "CONFIRMED",
                        accepted_terms       = bool(row.get("accepted_terms",       False)),
                        accepted_data_sharing= bool(row.get("accepted_data_sharing",False)),
                        accepted_marketing   = bool(row.get("accepted_marketing",   False)),
                        digital_badge_issued = bool(row.get("digital_badge_issued", False)),
                        onsite_badge_printed = bool(row.get("onsite_badge_printed", False)),
                    )

                    Badge.objects.create(
                        attendee   = attendee,
                        badge_type = str(row.get("ticket_type") or "").strip().upper(),
                    )

                    created += 1

                except IntegrityError as e:
                    logger.warning(f"IntegrityError for email {email}: {e}", exc_info=True)
                    skipped += 1

                except Exception as e:
                    logger.error(f"Unexpected error for row {row}: {e}", exc_info=True)
                    skipped += 1

    return {
        "created"    : created,
        "skipped"    : skipped,
        "total_valid": len(rows),
    }

@shared_task(
    bind=True,
    rate_limit='100/m',  # max 100 emails per minute
    max_retries=3
)
def send_invite_email(self,email, token):
    try:
        logger.info(f"Attempting to send invitation email to {email}")
        link = f"http://127.0.0.1:8000/register/{token}/"

        send_mail(
            subject="You're Invited!",
            message=f"Click to register: {link}",
            from_email="abhinand@veuz.in",
            recipient_list=[email],
        )
        logger.info(f"Successfully sent invitation email to {email}")
    except Exception as exc:
        logger.error(f"Error sending invitation email to {email}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True)
def process_invitations_batch(self, entries, exhibitor_id):
    from .models import Attendee, Exhibitor
    from django.db import transaction

    exhibitor = Exhibitor.objects.get(id=exhibitor_id)
    event = exhibitor.event

    # 1️⃣ Collect emails
    incoming_emails = {
        (e.get("email") or "").strip().lower()
        for e in entries if (e.get("email") or "").strip()
    }

    # 2️⃣ Fetch existing attendees
    existing_qs = Attendee.objects.filter(
        event=event,
        email__in=incoming_emails
    )

    existing_map = {a.email: a for a in existing_qs}

    # 3️⃣ Prepare lists
    to_create = []
    to_email_existing = []

    for entry in entries:
        email = (entry.get("email") or "").strip().lower()
        first_name = (entry.get("first_name") or "").strip()
        last_name = (entry.get("last_name") or "").strip()
        ticket_type= (entry.get("ticket_type") or "").strip()

        if not email or not first_name or not last_name:
            continue

        if email in existing_map:
            attendee = existing_map[email]

            # OPTIONAL: reset status if you want re-invite behavior
            if attendee.status != Attendee.Status.INVITED:
                attendee.status = Attendee.Status.INVITED
                attendee.save(update_fields=["status"])

            to_email_existing.append(attendee)

        else:
            to_create.append(Attendee(
                event=event,
                exhibitor=exhibitor,
                email=email,
                first_name=first_name,
                last_name=last_name,
                status=Attendee.Status.INVITED
            ))

    # 4️⃣ Bulk insert new attendees
    created = []
    CHUNK = 500

    logger.info(f"Attempting to bulk create {len(to_create)} attendees.")

    for i in range(0, len(to_create), CHUNK):
        created_batch = Attendee.objects.bulk_create(
            to_create[i:i+CHUNK]
        )
        created += created_batch

    logger.info(f"Successfully created {len(created)} attendees.")

    # 5️⃣ Combine ALL for email (THIS WAS MISSING)
    all_for_email = created + to_email_existing
    
    print(all_for_email,"----------all emaill")

    logger.info(f"Total emails to send: {len(all_for_email)}")

    # 6️⃣ Send emails
    sent_count = 0

    for i in range(0, len(all_for_email), 100):
        batch = all_for_email[i:i+100]

        for attendee in batch:
            if attendee.pk:
                send_invite_email.delay(
                    attendee.email,
                    str(attendee.invite_token)
                )
                sent_count += 1
            else:
                logger.warning(
                    f"Attendee {attendee.email} has no PK, skipping email."
                )

    logger.info(f"Queued {sent_count} invitation emails.")