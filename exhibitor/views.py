# =============================================================================
# IMPORTS
# =============================================================================
import json
import traceback

import pandas as pd
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from .forms import CreateBadgeForm
from .models import User, Exhibitor, Event, Badge, Attendee
from math import ceil
from django.core.paginator import Paginator
from .tasks import bulk_upload_save_task
from celery.result import AsyncResult


# =============================================================================
# AUTH
# =============================================================================

def Login(request):
    """Handle exhibitor login via email + password."""
    if request.method == "POST":
        email    = request.POST.get("email")
        password = request.POST.get("password")
        user     = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            return redirect("home")

        return render(request, "login.html", {"error": "Invalid credentials"})

    return render(request, "login.html")


# =============================================================================
# DASHBOARD
# =============================================================================
@login_required(login_url="login")
def index(request):
    exhibitor = request.user.exhibitor
    total_pass = exhibitor.pass_limit
    used_pass = Badge.objects.filter(attendee__exhibitor=exhibitor).count()

    stats = Attendee.objects.filter(exhibitor=exhibitor).aggregate(
        confirmed=Count("id", filter=Q(status="CONFIRMED")),
        pending=Count("id", filter=Q(status="PENDING")),
        invited=Count("id", filter=Q(status="INVITED")),
    )

    registrations_qs = Attendee.objects.filter(
        exhibitor=exhibitor
    ).select_related("badge", "exhibitor").order_by("-id")

    # Get page size from request or default to 10
    page_size = request.GET.get('page_size', 10)
    try:
        page_size = int(page_size)
        if page_size not in [10, 25, 50, 100]:
            page_size = 10
    except ValueError:
        page_size = 10

    # Pagination
    page_number = request.GET.get("page", 1)
    paginator = Paginator(registrations_qs, page_size)
    registrations = paginator.get_page(page_number)

    return render(request, "index.html", {
        "registrations": registrations,
        "used_pass": used_pass,
        "total_pass": total_pass,
        "confirmed_count": stats["confirmed"],
        "pending_count": stats["pending"],
        "invited_count": stats["invited"],
        "current_page_size": page_size,  # Pass to template
    })

# =============================================================================
# SINGLE BADGE CREATION
# =============================================================================

# Maps form ticket_type strings → Attendee.AttendeeType enum values
TICKET_TYPE_MAP = {
    "VIP"      : Attendee.AttendeeType.VIP,
    "EXHIBITOR": Attendee.AttendeeType.EXHIBITOR,
    "VISITOR"  : Attendee.AttendeeType.VISITOR,
}

# Maps database error snippets → user-friendly messages
DB_ERROR_MESSAGES = {
    "UNIQUE constraint failed": {
        "email": "This email address is already registered."
    },
    "NOT NULL constraint"     : "Please fill in all required fields.",
    "value too long"          : "One of the entered values is too long.",
    "DataError"               : "One of the entered values is too long.",
}


def _friendly_db_error(error_str):
    """Convert a raw database error string into a user-friendly message."""
    if "UNIQUE constraint failed" in error_str and "email" in error_str:
        return "This email address is already registered."
    if "NOT NULL constraint" in error_str:
        return "Please fill in all required fields."
    if "value too long" in error_str or "DataError" in error_str:
        return "One of the entered values is too long."
    return "Something went wrong. Please try again or contact support."


@login_required
@require_http_methods(["POST"])
def create_single_badge(request):
    """
    Create one Attendee + Badge for the logged-in exhibitor.

    Flow:
      1. Validate form
      2. Check pass limit
      3. Create Attendee + Badge inside a transaction
      4. Return JSON success / error
    """
    # ── 1. Form validation ──────────────────────────────────────────────────
    form = CreateBadgeForm(request.POST)
    if not form.is_valid():
        errors = {field: msgs[0] for field, msgs in form.errors.items()}
        return JsonResponse({"success": False, "errors": errors}, status=400)

    # ── 2. Resolve exhibitor ────────────────────────────────────────────────
    try:
        exhibitor = request.user.exhibitor
    except Exception:
        return JsonResponse(
            {"success": False, "errors": {"__all__": "User is not an exhibitor"}},
            status=403,
        )

    # ── 3. Pass limit check ─────────────────────────────────────────────────
    used = Badge.objects.filter(attendee__exhibitor=exhibitor).count()
    if used >= exhibitor.pass_limit:
        return JsonResponse({
            "success": False,
            "errors" : f"Pass limit reached ({exhibitor.pass_limit}). Cannot create more badges.",
        })

    # ── 4. Create Attendee + Badge ──────────────────────────────────────────
    ticket_type = form.cleaned_data["ticket_type"]

    try:
        with transaction.atomic():
            attendee = Attendee.objects.create(
                event                 = exhibitor.event,
                exhibitor             = exhibitor,
                first_name            = form.cleaned_data["first_name"],
                last_name             = form.cleaned_data["last_name"],
                email                 = form.cleaned_data["email"],
                mobile_number         = form.cleaned_data["mobile_number"],
                job_title             = form.cleaned_data["job_title"],
                company_name          = form.cleaned_data["company_name"],
                country_of_residence  = form.cleaned_data["country_of_residence"],
                nationality           = form.cleaned_data["nationality"],
                attendee_type         = TICKET_TYPE_MAP[ticket_type],
                source                = "Exhibitor Portal",
                status                = Attendee.Status.PENDING,
                accepted_terms        = form.cleaned_data["accepted_terms"],
                accepted_data_sharing = form.cleaned_data["accepted_data_sharing"],
                accepted_marketing    = form.cleaned_data.get("accepted_marketing", False),
            )

            Badge.objects.create(
                attendee    = attendee,
                badge_type  = ticket_type,
                ticket_class= f"{ticket_type} Pass",
            )

    except Exception as e:
        return JsonResponse(
            {"success": False, "errors": _friendly_db_error(str(e))},
            status=500,
        )

    return JsonResponse(
        {"success": True, "message": "Badge registered successfully."},
        status=201,
    )


# =============================================================================
# BULK UPLOAD — STEP 1: Get columns from uploaded file
# =============================================================================

@login_required
@require_POST
def get_columns(request):
    """
    Return the column headers from an uploaded CSV / Excel file.
    Used to populate the field-mapping UI before preview.
    """
    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

    if file.name.endswith(".csv"):
        df = pd.read_csv(file, nrows=1)
    else:
        df = pd.read_excel(file, nrows=1)


    return JsonResponse({"columns": list(df.columns)})


# =============================================================================
# BULK UPLOAD — STEP 2: Preview + validate rows
# =============================================================================

def _clean(value):
    """Return a stripped string, or None for NaN / blank values."""
    if pd.isna(value):
        return None
    return str(value).strip() or None


def _validate_row(row, existing_emails):
    """
    Validate a single spreadsheet row.
    Returns a list of error strings (empty = valid).
    """
    errors = []

    first_name = row.get("first_name")
    email = row.get("email")
    ticket_type = row.get("ticket_type")
    accepted_terms = row.get("accepted_terms")

    # Required field validations
    if pd.isna(first_name) or not str(first_name).strip():
        errors.append("First name required")

    if pd.isna(email) or "@" not in str(email):
        errors.append("Invalid email")
    elif str(email).strip().lower() in existing_emails:
        errors.append("Email already exists")

    if not ticket_type or pd.isna(ticket_type):
        errors.append("Ticket type required")

    if pd.isna(accepted_terms) or str(accepted_terms).lower() not in ("true", "1", "yes"):
        errors.append("Terms must be accepted")

    # Note: accepted_data_sharing and accepted_marketing are optional
    # They don't cause validation errors if missing

    return errors


@login_required
@require_POST
def bulk_upload_preview(request):
    """
    Parse an uploaded file, apply optional column mapping, validate every row,
    and return a preview payload for the UI.
    """
    file = request.FILES.get("file")
    mapping = json.loads(request.POST.get("mapping", "{}"))
    page = int(request.POST.get("page", 1))
    page_size = int(request.POST.get("page_size", 50))

    if not file:
        return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

    try:
        # Clear old session data when uploading new file
        if "bulk_preview_data" in request.session:
            del request.session["bulk_preview_data"]
        
        # ── Parse file ──────────────────────────────────────────────────────
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        df.columns = [col.strip() for col in df.columns]

        if mapping:
            df.rename(columns=mapping, inplace=True)

        df = df.where(pd.notnull(df), None)

        # Load all existing emails once (avoid per-row DB hits)
        existing_emails = set(
            Attendee.objects.values_list("email", flat=True)
        )

        # ── Build preview rows ──────────────────────────────────────────────
        preview_data = []
        valid_count = 0
        invalid_count = 0

        for index, row in df.iterrows():
            # Create a row dict for validation
            row_dict = {
                "first_name": row.get("first_name"),
                "email": row.get("email"),
                "ticket_type": row.get("ticket_type"),
                "accepted_terms": row.get("accepted_terms"),
            }
            errors = _validate_row(row_dict, existing_emails)
            status = "valid" if not errors else "invalid"

            if status == "valid":
                valid_count += 1
            else:
                invalid_count += 1

            preview_data.append({
                "id": index,
                "row": index + 1,
                "first_name": _clean(row.get("first_name")),
                "last_name": _clean(row.get("last_name")),
                "email": _clean(row.get("email")),
                "mobile_number": _clean(row.get("mobile_number")),
                "country": _clean(row.get("country")),
                "nationality": _clean(row.get("nationality")),
                "company_name": _clean(row.get("company_name")),
                "job_title": _clean(row.get("job_title")),
                "ticket_type": _clean(row.get("ticket_type")),
                "accepted_terms": _clean(row.get("accepted_terms")),
                "accepted_data_sharing": _clean(row.get("accepted_data_sharing", False)),
                "accepted_marketing": _clean(row.get("accepted_marketing", False)),
                "status": status,
                "errors": errors,
            })

        # Store in session
        request.session["bulk_preview_data"] = preview_data
        request.session.modified = True

        total_records = len(preview_data)
        total_pages = ceil(total_records / page_size)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_data = preview_data[start:end]

        return JsonResponse({
            "success": True,
            "data": paginated_data,
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "total": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# =============================================================================
# BULK UPLOAD — STEP 3: Save valid rows
# =============================================================================

@login_required
@require_POST
def bulk_upload_save(request):
    preview_data = request.session.get("bulk_preview_data", [])

    if not preview_data:
        return JsonResponse({
            "success": False,
            "errors": "No data found in session."
        }, status=400)

    # 🚀 Send to Celery
    task = bulk_upload_save_task.delay(
        preview_data,
        request.user.exhibitor.id
    )

    # Clear session immediately (optional)
    request.session.pop("bulk_preview_data", None)

    return JsonResponse({
        "success": True,
        "task_id": task.id,  # 🔥 important for tracking
        "message": "Processing started in background"
    })



# =============================================================================
# UTILITY — Real-time email duplicate check (called from frontend)
# =============================================================================

@login_required
@require_POST
def validate_email(request):
    """Return whether an email is already registered as an Attendee."""
    data  = json.loads(request.body)
    email = data.get("email", "").strip().lower()

    exists = Attendee.objects.filter(email=email).exists()
    return JsonResponse({"exists": exists})

@login_required
@require_POST
def bulk_update_session(request):
    """Update session data with edited rows."""
    data = json.loads(request.body)
    updates = data.get("rows", [])

    preview_data = request.session.get("bulk_preview_data", [])
    
    if not preview_data:
        return JsonResponse({"success": False, "error": "No session data found"}, status=400)
    
    # Convert to dict for O(1) lookup
    preview_map = {row["id"]: row for row in preview_data}

    for upd in updates:
        row_id = upd["id"]
        if row_id in preview_map:
            # Update the row with new data
            preview_map[row_id].update(upd)
            
            # Re-validate with existing emails (excluding current email)
            current_email = upd.get("email", "")
            existing_emails = set(
                Attendee.objects.exclude(email=current_email)
                .values_list("email", flat=True)
            )
            
            # Create a copy for validation
            row_copy = preview_map[row_id].copy()
            errors = _validate_row(row_copy, existing_emails)
            
            preview_map[row_id]["errors"] = errors
            preview_map[row_id]["status"] = "valid" if not errors else "invalid"

    # Save back to session
    request.session["bulk_preview_data"] = list(preview_map.values())
    
    # Update counts in session for quick access
    valid_count = sum(1 for row in request.session["bulk_preview_data"] if row["status"] == "valid")
    invalid_count = sum(1 for row in request.session["bulk_preview_data"] if row["status"] == "invalid")
    request.session["bulk_valid_count"] = valid_count
    request.session["bulk_invalid_count"] = invalid_count
    request.session["bulk_total_records"] = len(preview_data)
    
    request.session.modified = True

    return JsonResponse({"success": True})

@login_required
def bulk_task_status(request, task_id):
    result = AsyncResult(task_id)
    
    if result.state == "PENDING":
        return JsonResponse({"state": "PENDING"})
    
    elif result.state == "SUCCESS":
        return JsonResponse({
            "state": "SUCCESS",
            **result.result  # spreads created, skipped, total_valid
        })
    
    elif result.state == "FAILURE":
        return JsonResponse({
            "state": "FAILURE",
            "error": str(result.result)
        }, status=500)
    
    return JsonResponse({"state": result.state})