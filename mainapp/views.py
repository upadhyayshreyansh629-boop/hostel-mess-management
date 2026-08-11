from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Sum
from django.conf import settings
from django.core.mail import send_mail
from calendar import monthrange
from decimal import Decimal
from datetime import date, datetime, timedelta

from .models import (
    Student,
    FeePayment,
    Expense,
    MealAttendance,
    MonthlyBill,
    CreditRefund,
    MessVacation,
)


# ============================================================
# ADMIN-ONLY ACCESS
# ============================================================

def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("admin_login")
        if not request.user.is_staff:
            return redirect("student_dashboard")
        return view_func(request, *args, **kwargs)
    return wrapper


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def money(value):
    """
    Convert value into Decimal with 2 decimal places.
    """
    return Decimal(value or "0.00").quantize(
        Decimal("0.01")
    )


def get_month_absent_days(student, month):
    """Count full absent days, excluding days when the mess was closed."""
    month_start = month.replace(day=1)
    month_end = date(
        month.year,
        month.month,
        monthrange(month.year, month.month)[1]
    )

    vacation_ranges = MessVacation.objects.filter(
        mess_closed=True,
        start_date__lte=month_end,
        end_date__gte=month_start,
    ).values_list("start_date", "end_date")

    vacation_dates = set()
    for start_date, end_date in vacation_ranges:
        current = max(start_date, month_start)
        end = min(end_date, month_end)
        while current <= end:
            vacation_dates.add(current)
            current += timedelta(days=1)

    records = MealAttendance.objects.filter(
        student=student,
        date__year=month.year,
        date__month=month.month,
        breakfast=False,
        lunch=False,
        dinner=False,
    )

    return sum(
        1 for record in records
        if record.date not in vacation_dates
    )


def get_paid_amount(student, month):
    """
    Get actual money collected from FeePayment.
    Only Paid payments are counted.
    """

    return FeePayment.objects.filter(
        student=student,
        month=month,
        status="Paid"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")


def get_bill_gross_amount(bill):
    """
    Amount payable after food adjustment,
    BEFORE previous-month credit.

    Example:

    Monthly Fee = 2500
    Food Adjustment = 100

    Gross Bill = 2400
    """

    gross_amount = (
        bill.monthly_fee
        - bill.food_adjustment
    )

    if gross_amount < Decimal("0.00"):
        gross_amount = Decimal("0.00")

    return money(gross_amount)


def get_bill_extra_amount(bill):
    """
    Actual extra payment of CURRENT month's payment.

    Important:
    Previous credit applied to this bill is NOT treated
    as a new extra payment.

    Therefore calculation is based on gross bill amount
    before previous credit.
    """

    gross_amount = get_bill_gross_amount(bill)

    extra_amount = (
        bill.paid_amount
        - gross_amount
    )

    if extra_amount < Decimal("0.00"):
        extra_amount = Decimal("0.00")

    return money(extra_amount)


def update_bill_payment_values(bill):
    """
    Update actual paid amount, balance and extra paid.
    """

    paid_amount = get_paid_amount(
        bill.student,
        bill.month
    )

    bill.paid_amount = money(
        paid_amount
    )

    # --------------------------------------------------------
    # Gross bill before previous credit
    # --------------------------------------------------------

    gross_amount = get_bill_gross_amount(
        bill
    )

    # --------------------------------------------------------
    # Final amount can already contain previous credit
    # --------------------------------------------------------

    final_amount = money(
        bill.final_amount
    )

    balance = (
        final_amount
        - bill.paid_amount
    )

    if balance < Decimal("0.00"):
        balance = Decimal("0.00")

    bill.balance = money(
        balance
    )

    # --------------------------------------------------------
    # Extra payment is calculated BEFORE previous credit
    # --------------------------------------------------------

    extra_paid = (
        bill.paid_amount
        - gross_amount
    )

    if extra_paid < Decimal("0.00"):
        extra_paid = Decimal("0.00")

    bill.extra_paid = money(
        extra_paid
    )

    bill.save(
        update_fields=[
            "paid_amount",
            "balance",
            "extra_paid",
        ]
    )


# ============================================================
# STUDENT EMAIL HELPER
# ============================================================

def send_student_credentials_email(student, username, password, reset=False):
    """
    Send the student's portal credentials only to the email
    address stored on that student record.

    SMTP settings are read from Django settings/environment.
    If email is not configured, the student is still created and
    the admin can see the credentials on the credentials page.
    """
    subject = (
        "Your Hostel Mess Management Student Portal Credentials"
        if not reset
        else "Your Hostel Mess Management Password Has Been Reset"
    )

    message = f"""Dear {student.name},

{"Your student account has been created successfully." if not reset else "Your student portal login has been reset successfully."}

Student Details
---------------
Name: {student.name}
Student ID / Roll No.: {student.student_id}

Student Portal Login
--------------------
Username: {username}
Initial Password: {password}

Please log in and change your password after your first login.

Regards,
Hostel Mess Management
"""

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if not from_email:
        return False, "Email sender is not configured."

    try:
        send_mail(
            subject,
            message,
            from_email,
            [student.email],
            fail_silently=False,
        )
        return True, ""
    except Exception as exc:
     print("EMAIL ERROR:", repr(exc))
    return False, str(exc)



def send_fee_payment_email(payment, updated=False):
    """
    Send a payment confirmation/notification only to the email
    address belonging to the student whose payment was recorded.
    """

    student = payment.student

    subject = (
        "Mess Fee Payment Updated - Hostel Mess Management"
        if updated
        else "Mess Fee Payment Received - Hostel Mess Management"
    )

    # -----------------------------
    # Month formatting
    # -----------------------------
    month_value = payment.month

    if isinstance(month_value, str):
        try:
            month_value = datetime.strptime(
                month_value,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            month_value = None

    if month_value:
        month_label = month_value.strftime("%B %Y")
    else:
        month_label = str(payment.month)

    # -----------------------------
    # Payment date formatting
    # -----------------------------
    payment_date = payment.payment_date

    if isinstance(payment_date, str):
        try:
            payment_date = datetime.strptime(
                payment_date,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            try:
                payment_date = datetime.strptime(
                    payment_date,
                    "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                payment_date = None

    if payment_date:
        formatted_payment_date = payment_date.strftime(
            "%d %B %Y"
        )
    else:
        formatted_payment_date = str(
            payment.payment_date
        )

    status = payment.status

    # -----------------------------
    # Monthly bill
    # -----------------------------
    bill = MonthlyBill.objects.filter(
        student=student,
        month=payment.month
    ).first()

    balance = None

    if bill:
        update_bill_payment_values(bill)
        bill.refresh_from_db()
        balance = money(bill.balance)

    total_paid = get_paid_amount(
        student,
        payment.month
    )

    balance_line = (
        f"Current Balance: ₹{balance:.2f}\n"
        if balance is not None
        else
        "Current Balance: The monthly bill has not been generated yet.\n"
    )

    # -----------------------------
    # Email message
    # -----------------------------
    message = f"""Dear {student.name},

Your mess fee payment has been {"updated" if updated else "recorded"} successfully.

Payment Details

Receipt No.: {payment.receipt_no}
Month: {month_label}
Amount: ₹{money(payment.amount):.2f}
Payment Date: {formatted_payment_date}
Payment Method: {payment.payment_method}
Status: {status}


{balance_line}

You can log in to your Student Portal to view your payment
and monthly bill details.

Regards,
Hostel Mess Management
"""

    # -----------------------------
    # Email configuration
    # -----------------------------
    from_email = getattr(
        settings,
        "DEFAULT_FROM_EMAIL",
        None
    )

    if not from_email:
        return False, "Email sender is not configured."

    if not student.email:
        return False, "Student email is not configured."

    try:

        send_mail(
            subject,
            message,
            from_email,
            [student.email],
            fail_silently=False,
        )

        return True, ""

    except Exception as exc:
        print("EMAIL ERROR:", repr(exc))
    return False, str(exc)
    return False, str(exc)

# ============================================================
# ADMIN LOGIN
# ============================================================

def admin_login(request):

    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("dashboard")
        return redirect("student_dashboard")

    if request.method == "POST":

        username = request.POST.get(
            "username",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
        )

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None and user.is_staff:

            login(
                request,
                user
            )

            return redirect("dashboard")

        return render(
            request,
            "mainapp/admin_login.html",
            {
                "error": "Invalid username or password."
            }
        )

    return render(
        request,
        "mainapp/admin_login.html"
    )


# ============================================================
# DASHBOARD
# ============================================================

@admin_required
def dashboard(request):

    # Dashboard is month-wise. Previous months remain available in
    # their own reports but are not mixed into the current month.
    selected_month = request.GET.get(
        "month",
        timezone.localdate().strftime("%Y-%m")
    ).strip()

    try:
        year, month = selected_month.split("-")
        year = int(year)
        month = int(month)
        month_date = date(year, month, 1)
    except (ValueError, TypeError):
        month_date = timezone.localdate().replace(day=1)
        selected_month = month_date.strftime("%Y-%m")

    month_start = month_date
    month_end = date(
        year,
        month,
        monthrange(year, month)[1]
    )

    total_students = Student.objects.filter(
        is_active=True,
        mess_joining_date__lte=month_end,
    ).filter(
        Q(mess_leaving_date__isnull=True)
        | Q(mess_leaving_date__gte=month_start)
    ).count()

    total_fees = FeePayment.objects.filter(
        month=month_date,
        status="Paid"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    total_food_expense = Expense.objects.filter(
        expense_type="Food",
        expense_date__gte=month_start,
        expense_date__lte=month_end,
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    total_labour_expense = Expense.objects.filter(
        expense_type="Labour",
        expense_date__gte=month_start,
        expense_date__lte=month_end,
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    total_other_expense = Expense.objects.filter(
        expense_type="Other",
        expense_date__gte=month_start,
        expense_date__lte=month_end,
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    total_refunds = CreditRefund.objects.filter(
        transaction_type="Refund",
        processed_date__gte=month_start,
        processed_date__lte=month_end,
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    total_credit = CreditRefund.objects.filter(
        transaction_type="Credit",
        processed_date__gte=month_start,
        processed_date__lte=month_end,
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    net_collection = (
        total_fees - total_refunds
    ).quantize(Decimal("0.01"))

    vacations = MessVacation.objects.filter(
        start_date__lte=month_end,
        end_date__gte=month_start,
    ).order_by("start_date")

    return render(
        request,
        "mainapp/dashboard.html",
        {
            "total_students": total_students,
            "total_fees": total_fees,
            "total_food_expense": total_food_expense,
            "total_labour_expense": total_labour_expense,
            "total_other_expense": total_other_expense,
            "total_refunds": total_refunds,
            "total_credit": total_credit,
            "net_collection": net_collection,
            "selected_month": selected_month,
            "selected_month_label": month_date.strftime("%B %Y"),
            "vacations": vacations,
        }
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

def admin_logout(request):

    logout(request)

    return redirect("admin_login")


# ============================================================
# STUDENT LIST
# ============================================================

@admin_required
def student_list(request):

    students = Student.objects.all().order_by(
        "year",
        "name"
    )

    year = request.GET.get(
        "year",
        ""
    )

    search = request.GET.get(
        "search",
        ""
    ).strip()

    if year:

        students = students.filter(
            year=year
        )

    if search:

        students = students.filter(
            Q(name__icontains=search)
            |
            Q(student_id__icontains=search)
            |
            Q(room_no__icontains=search)
        )

    return render(
        request,
        "mainapp/students/student_list.html",
        {
            "students": students,

            "selected_year": year,

            "search": search,
        }
    )


# ============================================================
# ADD STUDENT
# ============================================================

@admin_required
def student_add(request):

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        student_id = request.POST.get("student_id", "").strip()
        year = request.POST.get("year")
        branch = request.POST.get("branch", "").strip()
        room_no = request.POST.get("room_no", "").strip()
        email = request.POST.get("email", "").strip().lower()
        mobile = request.POST.get("mobile", "").strip()
        joining_date = request.POST.get("mess_joining_date")
        monthly_fee = request.POST.get("monthly_fee", "2500")

        if Student.objects.filter(student_id=student_id).exists():
            messages.error(request, "Student ID already exists.")
            return redirect("student_add")

        if Student.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return redirect("student_add")

        if User.objects.filter(username=email).exists():
            messages.error(request, "This email is already used as a login ID.")
            return redirect("student_add")

        with transaction.atomic():
            student = Student.objects.create(
                name=name,
                student_id=student_id,
                year=year,
                branch=branch,
                room_no=room_no,
                email=email,
                mobile=mobile,
                mess_joining_date=joining_date,
                monthly_fee=monthly_fee,
                is_active=True,
            )

            # Login username = student's email.
            # Initial password = student's roll/student ID.
            password = student_id

            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=name[:150],
                is_staff=False,
                is_active=True,
            )

        email_sent, email_error = send_student_credentials_email(
            student,
            user.username,
            password,
            reset=False,
        )

        if email_sent:
            messages.success(
                request,
                f"Student added successfully. Login credentials were sent to {student.email}."
            )
        else:
            messages.warning(
                request,
                f"Student added successfully, but the credentials email could not be sent. "
                f"Check Email/SMTP settings. You can use the credentials shown below."
            )

        return render(
            request,
            "mainapp/students/student_credentials.html",
            {
                "student": student,
                "login_id": user.username,
                "temporary_password": password,
                "email_sent": email_sent,
                "email_error": email_error if not email_sent else "",
            }
        )

    return render(request, "mainapp/students/student_form.html")


# ============================================================
# CREATE / RESET STUDENT LOGIN
# ============================================================

@admin_required
def student_credentials(request, id):

    if request.method != "POST":
        return redirect("student_list")

    student = get_object_or_404(Student, id=id)

    user = User.objects.filter(
        email=student.email,
        is_staff=False
    ).first()

    if user is None:
        user = User.objects.filter(
            username=student.student_id,
            is_staff=False
        ).first()

    if user is None:
        user = User.objects.create_user(
            username=student.email,
            email=student.email,
            first_name=student.name[:150],
            is_staff=False,
            is_active=True,
        )

    password = student.student_id

    user.username = student.email
    user.set_password(password)
    user.email = student.email
    user.first_name = student.name[:150]
    user.is_staff = False
    user.is_active = True
    user.save()

    email_sent, email_error = send_student_credentials_email(
        student,
        user.username,
        password,
        reset=True,
    )

    if email_sent:
        messages.success(
            request,
            f"Login credentials reset and emailed to {student.email}."
        )
    else:
        messages.warning(
            request,
            "Login was reset, but the credentials email could not be sent. "
            "Check Email/SMTP settings."
        )

    return render(
        request,
        "mainapp/students/student_credentials.html",
        {
            "student": student,
            "login_id": user.username,
            "temporary_password": password,
            "reset": True,
            "email_sent": email_sent,
            "email_error": email_error if not email_sent else "",
        }
    )


# ============================================================
# EDIT STUDENT
# ============================================================

@admin_required
def student_edit(request, id):

    student = get_object_or_404(Student, id=id)

    if request.method == "POST":

        old_student_id = student.student_id
        old_email = student.email

        name = request.POST.get("name", "").strip()
        student_id = request.POST.get("student_id", "").strip()
        year = request.POST.get("year")
        branch = request.POST.get("branch", "").strip()
        room_no = request.POST.get("room_no", "").strip()
        email = request.POST.get("email", "").strip().lower()
        mobile = request.POST.get("mobile", "").strip()
        joining_date = request.POST.get("mess_joining_date")
        leaving_date = request.POST.get("mess_leaving_date") or None
        monthly_fee = request.POST.get("monthly_fee", "2500")

        if Student.objects.filter(
            student_id=student_id
        ).exclude(id=student.id).exists():
            messages.error(request, "Student ID already exists.")
            return redirect("student_edit", id=student.id)

        if Student.objects.filter(
            email=email
        ).exclude(id=student.id).exists():
            messages.error(request, "Email already exists.")
            return redirect("student_edit", id=student.id)

        existing_user = User.objects.filter(
            Q(username=email) | Q(username=old_email),
            is_staff=False
        ).exclude(id__isnull=True).first()

        if existing_user is None:
            existing_user = User.objects.filter(
                username=old_student_id,
                is_staff=False
            ).first()

        conflicting = User.objects.filter(
            username=email
        ).exclude(
            id=existing_user.id if existing_user else None
        ).first()

        if conflicting:
            messages.error(request, "That email is already used by another login.")
            return redirect("student_edit", id=student.id)

        student.name = name
        student.student_id = student_id
        student.year = year
        student.branch = branch
        student.room_no = room_no
        student.email = email
        student.mobile = mobile
        student.mess_joining_date = joining_date
        student.mess_leaving_date = leaving_date
        student.monthly_fee = monthly_fee
        student.save()

        if existing_user:
            existing_user.username = email
            existing_user.email = email
            existing_user.first_name = name[:150]
            existing_user.save(update_fields=["username", "email", "first_name"])

        messages.success(request, "Student updated successfully.")
        return redirect("student_list")

    return render(
        request,
        "mainapp/students/student_form.html",
        {"student": student}
    )


# ============================================================
# TOGGLE STUDENT STATUS
# ============================================================

@admin_required
def student_toggle_status(request, id):

    student = get_object_or_404(
        Student,
        id=id
    )

    student.is_active = not student.is_active

    student.save()

    if student.is_active:

        messages.success(
            request,
            f"{student.name} has been activated."
        )

    else:

        messages.success(
            request,
            f"{student.name} has been deactivated."
        )

    return redirect(
        "student_list"
    )


# ============================================================
# FEE LIST
# ============================================================

@admin_required
def fee_list(request):

    payments = FeePayment.objects.select_related(
        "student"
    ).all().order_by(
        "-payment_date",
        "-id"
    )

    search = request.GET.get(
        "search",
        ""
    ).strip()

    month = request.GET.get(
        "month",
        ""
    ).strip()

    status = request.GET.get(
        "status",
        ""
    ).strip()

    if search:

        payments = payments.filter(
            Q(student__name__icontains=search)
            |
            Q(student__student_id__icontains=search)
            |
            Q(receipt_no__icontains=search)
        )

    if month:

        payments = payments.filter(
            month=month + "-01"
        )

    if status:

        payments = payments.filter(
            status=status
        )

    return render(
        request,
        "mainapp/fees/fee_list.html",
        {
            "payments": payments,

            "search": search,

            "month": month,

            "selected_status": status,
        }
    )


# ============================================================
# ADD FEE PAYMENT
# ============================================================

@admin_required
def fee_add(request):

    students = Student.objects.filter(
        is_active=True
    ).order_by(
        "year",
        "name"
    )

    if request.method == "POST":

        student_id = request.POST.get(
            "student"
        )

        month = request.POST.get(
            "month"
        )

        amount = request.POST.get(
            "amount"
        )

        payment_date = request.POST.get(
            "payment_date"
        )

        status = request.POST.get(
            "status"
        )

        payment_method = request.POST.get(
            "payment_method"
        )

        student = get_object_or_404(
            Student,
            id=student_id,
            is_active=True
        )

        last_payment = FeePayment.objects.order_by(
            "-id"
        ).first()

        if last_payment:

            next_number = (
                last_payment.id + 1
            )

        else:

            next_number = 1

        receipt_no = (
            f"MMS-{next_number:05d}"
        )

        payment = FeePayment.objects.create(

            student=student,

            month=f"{month}-01",

            amount=amount,

            payment_date=payment_date,

            status=status,

            receipt_no=receipt_no,

            payment_method=payment_method,
        )

        # Send the notification only to this student's registered email.
        email_sent, email_error = send_fee_payment_email(payment)

        if email_sent:
            messages.success(
                request,
                f"Fee payment saved successfully. "
                f"Receipt: {receipt_no}. "
                f"Payment confirmation sent to {student.email}."
            )
        else:
            messages.warning(
                request,
                f"Fee payment saved successfully. "
                f"Receipt: {receipt_no}. "
                f"Email could not be sent: {email_error}"
            )

        return redirect(
            "fee_list"
        )

    return render(
        request,
        "mainapp/fees/fee_form.html",
        {
            "students": students,

            "today": timezone.localdate(),
        }
    )


# ============================================================
# EDIT FEE PAYMENT
# ============================================================

@admin_required
def fee_edit(request, id):

    payment = get_object_or_404(
        FeePayment,
        id=id
    )

    students = Student.objects.filter(
        is_active=True
    ).order_by(
        "year",
        "name"
    )

    if request.method == "POST":

        student_id = request.POST.get(
            "student"
        )

        month = request.POST.get(
            "month"
        )

        amount = request.POST.get(
            "amount"
        )

        payment_date = request.POST.get(
            "payment_date"
        )

        status = request.POST.get(
            "status"
        )

        payment_method = request.POST.get(
            "payment_method"
        )

        student = get_object_or_404(
            Student,
            id=student_id
        )

        payment.student = student
        payment.month = f"{month}-01"
        payment.amount = amount
        payment.payment_date = payment_date
        payment.status = status
        payment.payment_method = payment_method

        payment.save()

        # Notify the same student's registered email after an admin update.
        email_sent, email_error = send_fee_payment_email(
            payment,
            updated=True
        )

        if email_sent:
            messages.success(
                request,
                f"Payment {payment.receipt_no} updated successfully. "
                f"Notification sent to {student.email}."
            )
        else:
            messages.warning(
                request,
                f"Payment {payment.receipt_no} updated successfully, "
                f"but email could not be sent: {email_error}"
            )

        return redirect(
            "fee_list"
        )

    return render(
        request,
        "mainapp/fees/fee_form.html",
        {
            "students": students,

            "payment": payment,

            "edit_mode": True,
        }
    )


# ============================================================
# ATTENDANCE
# ============================================================

@admin_required
def attendance(request):

    # ---------------------------------------------------------
    # VIEW MODE
    # ---------------------------------------------------------
    # daily  -> normal attendance marking screen
    # monthly -> complete selected month's attendance report
    # ---------------------------------------------------------

    view_mode = request.GET.get("view", "daily")

    if request.method == "POST":
        view_mode = "daily"

    # ---------------------------------------------------------
    # SELECTED DATE
    # ---------------------------------------------------------

    selected_date = (
        request.GET.get("date")
        or request.POST.get("date")
        or date.today().isoformat()
    )

    # The mess is closed during an active vacation. Attendance cannot
    # be marked for a closed date.
    try:
        attendance_date_obj = datetime.strptime(
            selected_date, "%Y-%m-%d"
        ).date()
    except ValueError:
        attendance_date_obj = None

    active_vacation = None
    if attendance_date_obj:
        active_vacation = MessVacation.objects.filter(
            mess_closed=True,
            start_date__lte=attendance_date_obj,
            end_date__gte=attendance_date_obj,
        ).first()

    if request.method == "POST" and active_vacation:
        messages.warning(
            request,
            "Mess is closed on this date because of a mess vacation. "
            "Attendance was not saved."
        )
        return redirect(
            f"{reverse('attendance')}?date={selected_date}"
            f"&year={request.POST.get('year', '')}"
        )

    # ---------------------------------------------------------
    # SELECTED MONTH
    # ---------------------------------------------------------

    selected_month = (
        request.GET.get("month")
        or request.POST.get("month")
        or selected_date[:7]
    )

    # ---------------------------------------------------------
    # YEAR FILTER
    # ---------------------------------------------------------

    selected_year = (
        request.GET.get("year", "")
        or request.POST.get("year", "")
    )

    # ---------------------------------------------------------
    # STUDENTS
    # ---------------------------------------------------------

    students = Student.objects.filter(
        is_active=True
    ).order_by(
        "year",
        "name"
    )

    if selected_year:
        students = students.filter(
            year=selected_year
        )

    # ---------------------------------------------------------
    # SAVE DAILY ATTENDANCE
    # ---------------------------------------------------------

    if request.method == "POST":

        for student in students:

            breakfast = (
                request.POST.get(
                    f"breakfast_{student.id}"
                ) == "on"
            )

            lunch = (
                request.POST.get(
                    f"lunch_{student.id}"
                ) == "on"
            )

            dinner = (
                request.POST.get(
                    f"dinner_{student.id}"
                ) == "on"
            )

            MealAttendance.objects.update_or_create(

                student=student,

                date=selected_date,

                defaults={
                    "breakfast": breakfast,
                    "lunch": lunch,
                    "dinner": dinner,
                }
            )

        messages.success(
            request,
            f"Attendance saved successfully for {selected_date}."
        )

        redirect_url = (
            f"/attendance/?date={selected_date}"
            f"&year={selected_year}"
        )

        return redirect(redirect_url)

    # ---------------------------------------------------------
    # DAILY ATTENDANCE RECORDS
    # ---------------------------------------------------------

    attendance_records = {}

    records = MealAttendance.objects.filter(
        student__in=students,
        date=selected_date
    )

    for record in records:
        attendance_records[record.student_id] = record

    # ---------------------------------------------------------
    # MONTHLY ATTENDANCE REPORT
    # ---------------------------------------------------------

    monthly_days = []
    monthly_records = {}
    monthly_summary = {}

    if view_mode == "monthly":

        try:
            month_start = datetime.strptime(
                selected_month,
                "%Y-%m"
            ).date()

        except (ValueError, TypeError):

            month_start = date.today().replace(day=1)

            selected_month = month_start.strftime("%Y-%m")

        # First day of next month
        if month_start.month == 12:
            next_month = month_start.replace(
                year=month_start.year + 1,
                month=1,
                day=1
            )
        else:
            next_month = month_start.replace(
                month=month_start.month + 1,
                day=1
            )

        total_days = (
            next_month - month_start
        ).days

        monthly_days = [
            month_start + timedelta(days=i)
            for i in range(total_days)
        ]

        records = MealAttendance.objects.filter(
            student__in=students,
            date__gte=month_start,
            date__lt=next_month
        )

        for record in records:

            if record.student_id not in monthly_records:
                monthly_records[record.student_id] = {}

            monthly_records[
                record.student_id
            ][record.date.isoformat()] = record

        # -----------------------------------------------------
        # SUMMARY PER STUDENT
        # -----------------------------------------------------

        for student in students:

            student_day_records = monthly_records.get(
                student.id,
                {}
            )

            student_records = [
                student_day_records.get(
                    day.isoformat()
                )
                for day in monthly_days
            ]

            breakfast_count = sum(
                1
                for record in student_records
                if record and record.breakfast
            )

            lunch_count = sum(
                1
                for record in student_records
                if record and record.lunch
            )

            dinner_count = sum(
                1
                for record in student_records
                if record and record.dinner
            )

            monthly_summary[student.id] = {
                "breakfast": breakfast_count,
                "lunch": lunch_count,
                "dinner": dinner_count,
                "total": (
                    breakfast_count
                    + lunch_count
                    + dinner_count
                ),
            }

    # ---------------------------------------------------------
    # CONTEXT
    # ---------------------------------------------------------

    context = {

        "students": students,

        # Daily
        "attendance_records": attendance_records,
        "selected_date": selected_date,

        # Filters
        "selected_year": selected_year,
        "selected_month": selected_month,

        # View
        "view_mode": view_mode,

        # Monthly report
        "monthly_days": monthly_days,
        "monthly_records": monthly_records,
        "monthly_summary": monthly_summary,
    }

    return render(
        request,
        "mainapp/attendance/attendance.html",
        context
    )


# ============================================================
# EXPENSE LIST
# ============================================================

@admin_required
def expense_list(request):

    expenses = Expense.objects.all().order_by(
        "-expense_date",
        "-id"
    )

    search = request.GET.get(
        "search",
        ""
    ).strip()

    expense_type = request.GET.get(
        "expense_type",
        ""
    ).strip()

    month = request.GET.get(
        "month",
        ""
    ).strip()

    if search:

        expenses = expenses.filter(
            Q(item_name__icontains=search)
            |
            Q(description__icontains=search)
        )

    if expense_type:

        expenses = expenses.filter(
            expense_type=expense_type
        )

    if month:

        expenses = expenses.filter(
            expense_date__year=month[:4],
            expense_date__month=month[5:7]
        )

    total_food = expenses.filter(
        expense_type="Food"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    total_labour = expenses.filter(
        expense_type="Labour"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    total_other = expenses.filter(
        expense_type="Other"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    return render(
        request,
        "mainapp/expenses/expense_list.html",
        {
            "expenses": expenses,

            "search": search,

            "selected_type": expense_type,

            "selected_month": month,

            "total_food": total_food,

            "total_labour": total_labour,

            "total_other": total_other,
        }
    )


# ============================================================
# ADD EXPENSE
# ============================================================

@admin_required
def expense_add(request):

    if request.method == "POST":

        expense_type = request.POST.get(
            "expense_type"
        )

        item_name = request.POST.get(
            "item_name"
        )

        amount = request.POST.get(
            "amount"
        )

        expense_date = request.POST.get(
            "expense_date"
        )

        description = request.POST.get(
            "description"
        )

        Expense.objects.create(

            expense_type=expense_type,

            item_name=item_name,

            amount=amount,

            expense_date=expense_date,

            description=description,
        )

        messages.success(
            request,
            "Expense added successfully."
        )

        return redirect(
            "expense_list"
        )

    return render(
        request,
        "mainapp/expenses/expense_form.html",
        {
            "today": timezone.localdate(),
        }
    )


# ============================================================
# EDIT EXPENSE
# ============================================================

@admin_required
def expense_edit(request, id):

    expense = get_object_or_404(
        Expense,
        id=id
    )

    if request.method == "POST":

        expense.expense_type = request.POST.get(
            "expense_type"
        )

        expense.item_name = request.POST.get(
            "item_name"
        )

        expense.amount = request.POST.get(
            "amount"
        )

        expense.expense_date = request.POST.get(
            "expense_date"
        )

        expense.description = request.POST.get(
            "description"
        )

        expense.save()

        messages.success(
            request,
            "Expense updated successfully."
        )

        return redirect(
            "expense_list"
        )

    return render(
        request,
        "mainapp/expenses/expense_form.html",
        {
            "expense": expense,

            "edit_mode": True,
        }
    )



# ============================================================
# MESS VACATION
# ============================================================

@admin_required
def vacation_list(request):

    vacations = MessVacation.objects.all().order_by(
        "-start_date",
        "-id"
    )

    return render(
        request,
        "mainapp/vacation/vacation_list.html",
        {
            "vacations": vacations,
            "today": timezone.localdate(),
        }
    )


@admin_required
def vacation_add(request):

    if request.method == "POST":

        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        reason = request.POST.get("reason", "").strip()
        description = request.POST.get("description", "").strip()

        if not start_date or not end_date:
            messages.error(request, "Please select both start and end dates.")
            return redirect("vacation_add")

        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Invalid vacation dates.")
            return redirect("vacation_add")

        if end < start:
            messages.error(request, "End date cannot be before start date.")
            return redirect("vacation_add")

        MessVacation.objects.create(
            start_date=start,
            end_date=end,
            reason=reason or "Mess Vacation",
            description=description,
            mess_closed=True,
        )

        messages.success(
            request,
            f"Mess vacation added from {start.strftime('%d %b %Y')} "
            f"to {end.strftime('%d %b %Y')}."
        )
        return redirect("vacation_list")

    return render(
        request,
        "mainapp/vacation/vacation_form.html",
        {"today": timezone.localdate()}
    )


@admin_required
def vacation_delete(request, id):

    vacation = get_object_or_404(MessVacation, id=id)

    if request.method == "POST":
        vacation.delete()
        messages.success(request, "Mess vacation deleted successfully.")

    return redirect("vacation_list")

# ============================================================
# MONTHLY BILL LIST
# ============================================================

@admin_required
def monthly_bill_list(request):

    selected_month = request.GET.get(
        "month",
        ""
    ).strip()

    bills = MonthlyBill.objects.select_related(
        "student"
    ).order_by(
        "student__year",
        "student__name"
    )

    if selected_month:

        try:

            year, month = selected_month.split("-")

            bills = bills.filter(
                month__year=int(year),
                month__month=int(month)
            )

        except (
            ValueError,
            TypeError
        ):

            selected_month = ""

    # --------------------------------------------------------
    # ALWAYS SYNC PAYMENT VALUES FROM FEE PAYMENTS
    # --------------------------------------------------------
    #
    # A student may pay after the monthly bill was generated.
    # The list must therefore show the latest actual collection
    # without requiring the admin to generate the bill again.
    # --------------------------------------------------------

    for bill in bills:

        bill.absent_days = get_month_absent_days(bill.student, bill.month)
        bill.save(update_fields=["absent_days"])

        update_bill_payment_values(bill)

        bill.extra_amount = money(
            get_bill_extra_amount(bill)
        )

    return render(
        request,
        "mainapp/monthly_bills/monthly_bill_list.html",
        {
            "bills": bills,

            "selected_month": selected_month,
        }
    )


# ============================================================
# APPLY FOOD ADJUSTMENT
# ============================================================

@admin_required
def apply_food_adjustment(request, id):

    if request.method != "POST":

        return redirect(
            "monthly_bill_list"
        )

    bill = get_object_or_404(
        MonthlyBill.objects.select_related(
            "student"
        ),
        id=id
    )

    # --------------------------------------------------------
    # PREVENT DOUBLE ADJUSTMENT
    # --------------------------------------------------------

    if bill.food_adjustment > Decimal("0.00"):

        messages.warning(
            request,
            "Food adjustment is already applied for this bill."
        )

        return redirect(
            f"{reverse('monthly_bill_list')}"
            f"?month={bill.month.strftime('%Y-%m')}"
        )

    year = bill.month.year
    month = bill.month.month

    month_start = bill.month.replace(
        day=1
    )

    month_end = bill.month.replace(
        day=monthrange(
            year,
            month
        )[1]
    )

    # --------------------------------------------------------
    # ACTIVE MESS STUDENTS
    # --------------------------------------------------------

    active_students = Student.objects.filter(

        mess_joining_date__lte=month_end,

        is_active=True

    ).filter(

        Q(
            mess_leaving_date__isnull=True
        )
        |
        Q(
            mess_leaving_date__gte=month_start
        )
    )

    student_count = active_students.count()

    if student_count == 0:

        messages.error(
            request,
            "No active mess students found for this month."
        )

        return redirect(
            f"{reverse('monthly_bill_list')}"
            f"?month={bill.month.strftime('%Y-%m')}"
        )

    # --------------------------------------------------------
    # FOOD EXPENSE
    # --------------------------------------------------------

    food_expense = Expense.objects.filter(

        expense_type="Food",

        expense_date__gte=month_start,

        expense_date__lte=month_end

    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    if food_expense <= Decimal("0.00"):

        messages.error(
            request,
            "No Food Expense found for this month."
        )

        return redirect(
            f"{reverse('monthly_bill_list')}"
            f"?month={bill.month.strftime('%Y-%m')}"
        )

    # --------------------------------------------------------
    # DAYS IN MONTH
    # --------------------------------------------------------

    total_days = monthrange(
        year,
        month
    )[1]

    # --------------------------------------------------------
    # FOOD COST PER STUDENT PER DAY
    # --------------------------------------------------------

    food_cost_per_day = (

        food_expense
        / Decimal(student_count)
        / Decimal(total_days)

    ).quantize(
        Decimal("0.01")
    )

    # --------------------------------------------------------
    # MAXIMUM 10 ABSENT DAYS
    # --------------------------------------------------------

    adjustment_days = min(
        bill.absent_days,
        10
    )

    # --------------------------------------------------------
    # FOOD ADJUSTMENT
    # --------------------------------------------------------

    food_adjustment = (

        food_cost_per_day
        * Decimal(adjustment_days)

    ).quantize(
        Decimal("0.01")
    )

    # --------------------------------------------------------
    # FINAL AMOUNT BEFORE PREVIOUS CREDIT
    # --------------------------------------------------------

    final_amount = (

        bill.monthly_fee
        - food_adjustment

    ).quantize(
        Decimal("0.01")
    )

    if final_amount < Decimal("0.00"):

        final_amount = Decimal("0.00")

    # --------------------------------------------------------
    # ACTUAL PAID AMOUNT
    # --------------------------------------------------------

    paid_amount = get_paid_amount(
        bill.student,
        bill.month
    )

    # --------------------------------------------------------
    # BALANCE
    # --------------------------------------------------------

    balance = (

        final_amount
        - paid_amount

    ).quantize(
        Decimal("0.01")
    )

    if balance < Decimal("0.00"):

        balance = Decimal("0.00")

    # --------------------------------------------------------
    # EXTRA PAID
    # --------------------------------------------------------

    extra_paid = (

        paid_amount
        - final_amount

    ).quantize(
        Decimal("0.01")
    )

    if extra_paid < Decimal("0.00"):

        extra_paid = Decimal("0.00")

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    bill.allowed_adjustment_days = (
        adjustment_days
    )

    bill.food_adjustment = (
        food_adjustment
    )

    bill.final_amount = (
        final_amount
    )

    bill.paid_amount = (
        paid_amount
    )

    bill.balance = (
        balance
    )

    bill.extra_paid = (
        extra_paid
    )

    bill.save(
        update_fields=[

            "allowed_adjustment_days",

            "food_adjustment",

            "final_amount",

            "paid_amount",

            "balance",

            "extra_paid",
        ]
    )

    messages.success(
        request,
        f"Food adjustment of ₹{food_adjustment} "
        f"applied for {adjustment_days} day(s)."
    )

    return redirect(
        f"{reverse('monthly_bill_list')}"
        f"?month={bill.month.strftime('%Y-%m')}"
    )


# ============================================================
# APPLY AVAILABLE PREVIOUS CREDITS
# ============================================================

def apply_available_credits(
    student,
    bill
):

    available_credits = CreditRefund.objects.filter(

        student=student,

        transaction_type="Credit",

        status__in=[
            "Available",
            "Partially Used"
        ],

        source_bill__month__lt=bill.month

    ).exclude(

        target_bill=bill

    ).order_by(
        "source_bill__month",
        "id"
    )

    total_credit_used = Decimal("0.00")

    for credit in available_credits:

        remaining_credit = (

            credit.amount
            - credit.used_amount

        ).quantize(
            Decimal("0.01")
        )

        if remaining_credit <= Decimal("0.00"):

            continue

        if bill.final_amount <= Decimal("0.00"):

            break

        # ----------------------------------------------------
        # AMOUNT TO USE
        # ----------------------------------------------------

        credit_to_use = min(

            remaining_credit,

            bill.final_amount

        )

        credit_to_use = money(
            credit_to_use
        )

        # ----------------------------------------------------
        # REDUCE FINAL BILL
        # ----------------------------------------------------

        bill.final_amount = (

            bill.final_amount
            - credit_to_use

        ).quantize(
            Decimal("0.01")
        )

        # ----------------------------------------------------
        # CREDIT USED
        # ----------------------------------------------------

        credit.used_amount = (

            credit.used_amount
            + credit_to_use

        ).quantize(
            Decimal("0.01")
        )

        total_credit_used += credit_to_use

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        if credit.used_amount >= credit.amount:

            credit.status = "Used"

        else:

            credit.status = "Partially Used"

        credit.target_bill = bill

        credit.save(
            update_fields=[
                "used_amount",
                "status",
                "target_bill",
            ]
        )

    # --------------------------------------------------------
    # UPDATE BILL CREDIT USED
    # --------------------------------------------------------

    if total_credit_used > Decimal("0.00"):

        bill.credit_used = (

            bill.credit_used
            + total_credit_used

        ).quantize(
            Decimal("0.01")
        )

    # --------------------------------------------------------
    # BALANCE
    # --------------------------------------------------------

    balance = (

        bill.final_amount
        - bill.paid_amount

    ).quantize(
        Decimal("0.01")
    )

    if balance < Decimal("0.00"):

        balance = Decimal("0.00")

    bill.balance = balance

    bill.save(
        update_fields=[
            "final_amount",
            "balance",
            "credit_used",
        ]
    )


# ============================================================
# PROCESS CREDIT / REFUND
# ============================================================

@admin_required
@transaction.atomic
def process_credit_refund(request, id):

    if request.method != "POST":
        return redirect("monthly_bill_list")

    bill = get_object_or_404(
        MonthlyBill.objects.select_related("student"),
        id=id
    )

    # ---------------------------------------------------------
    # REFUND ONLY APPLIES TO CURRENT EXTRA PAYMENT
    # ---------------------------------------------------------

    # Recalculate actual paid amount so the refund is based on
    # the latest FeePayment records.
    paid_amount = get_paid_amount(
        bill.student,
        bill.month
    )

    bill.paid_amount = money(paid_amount)

    # Gross bill = monthly fee after food adjustment,
    # before any previous-month credit.
    gross_amount = get_bill_gross_amount(bill)

    extra_amount = money(
        bill.paid_amount - gross_amount
    )

    if extra_amount <= Decimal("0.00"):
        messages.warning(
            request,
            "There is no extra payment available for refund."
        )

        return redirect(
            f"{reverse('monthly_bill_list')}"
            f"?month={bill.month.strftime('%Y-%m')}"
        )

    # ---------------------------------------------------------
    # PREVENT DUPLICATE REFUND / CREDIT
    # ---------------------------------------------------------

    existing_transaction = CreditRefund.objects.filter(
        source_bill=bill
    ).first()

    if existing_transaction:
        messages.warning(
            request,
            "Credit/Refund has already been processed for this bill."
        )

        return redirect(
            f"{reverse('monthly_bill_list')}"
            f"?month={bill.month.strftime('%Y-%m')}"
        )

    # ---------------------------------------------------------
    # CREATE REFUND TRANSACTION
    #
    # This is important because dashboard and transaction
    # history use CreditRefund records.
    # ---------------------------------------------------------

    CreditRefund.objects.create(
        source_bill=bill,
        student=bill.student,
        transaction_type="Refund",
        amount=extra_amount,
        used_amount=extra_amount,
        status="Completed",
        processed_date=timezone.localdate(),
        note="Amount refunded to student."
    )

    # ---------------------------------------------------------
    # UPDATE MONTHLY BILL
    # ---------------------------------------------------------

    bill.extra_paid = extra_amount
    bill.refund_amount = extra_amount
    bill.refund_date = timezone.localdate()
    bill.credit_status = "Refunded"

    # Keep the actual paid amount and original extra amount
    # visible for accounting/history.
    bill.balance = money(
        bill.final_amount - bill.paid_amount
    )

    if bill.balance < Decimal("0.00"):
        bill.balance = Decimal("0.00")

    bill.save(
        update_fields=[
            "paid_amount",
            "extra_paid",
            "refund_amount",
            "refund_date",
            "credit_status",
            "balance",
        ]
    )

    messages.success(
        request,
        f"₹{extra_amount} refund recorded successfully for "
        f"{bill.student.name}."
    )

    return redirect(
        f"{reverse('monthly_bill_list')}"
        f"?month={bill.month.strftime('%Y-%m')}"
    )


# ============================================================
# GENERATE MONTHLY BILLS
# ============================================================

@admin_required
def generate_monthly_bills(request):

    if request.method != "POST":

        return redirect(
            "monthly_bill_list"
        )

    selected_month = request.POST.get(
        "month",
        ""
    ).strip()

    if not selected_month:

        messages.error(
            request,
            "Please select a month."
        )

        return redirect(
            "monthly_bill_list"
        )

    try:

        year, month = selected_month.split("-")

        year = int(year)

        month = int(month)

        month_date = date(
            year,
            month,
            1
        )

    except (
        ValueError,
        TypeError
    ):

        messages.error(
            request,
            "Invalid month selected."
        )

        return redirect(
            "monthly_bill_list"
        )

    # --------------------------------------------------------
    # MONTH RANGE
    # --------------------------------------------------------

    month_start = month_date

    month_end = date(
        year,
        month,
        monthrange(
            year,
            month
        )[1]
    )

    # --------------------------------------------------------
    # ACTIVE MESS STUDENTS
    # --------------------------------------------------------

    students = Student.objects.filter(

        mess_joining_date__lte=month_end,

        is_active=True

    ).filter(

        Q(
            mess_leaving_date__isnull=True
        )
        |
        Q(
            mess_leaving_date__gte=month_start
        )
    )

    student_count = students.count()

    if student_count == 0:

        messages.error(
            request,
            "No active mess students found for this month."
        )

        return redirect(
            f"{reverse('monthly_bill_list')}"
            f"?month={selected_month}"
        )

    # --------------------------------------------------------
    # MONTHLY FOOD EXPENSE
    # --------------------------------------------------------

    food_total = Expense.objects.filter(

        expense_type="Food",

        expense_date__gte=month_start,

        expense_date__lte=month_end

    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    # --------------------------------------------------------
    # MONTHLY LABOUR EXPENSE
    # --------------------------------------------------------

    labour_total = Expense.objects.filter(

        expense_type="Labour",

        expense_date__gte=month_start,

        expense_date__lte=month_end

    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    # --------------------------------------------------------
    # MONTHLY OTHER EXPENSE
    # --------------------------------------------------------

    other_total = Expense.objects.filter(

        expense_type="Other",

        expense_date__gte=month_start,

        expense_date__lte=month_end

    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    # --------------------------------------------------------
    # SAME PER-STUDENT SHARE FOR EVERY STUDENT
    # --------------------------------------------------------

    food_per_student = (

        food_total
        / Decimal(student_count)

    ).quantize(
        Decimal("0.01")
    )

    labour_per_student = (

        labour_total
        / Decimal(student_count)

    ).quantize(
        Decimal("0.01")
    )

    other_per_student = (

        other_total
        / Decimal(student_count)

    ).quantize(
        Decimal("0.01")
    )

    # --------------------------------------------------------
    # CREATE / UPDATE MONTHLY BILLS
    # --------------------------------------------------------

    created_count = 0

    existing_count = 0

    for student in students:

        bill, created = MonthlyBill.objects.get_or_create(

            student=student,

            month=month_date,

            defaults={

                "monthly_fee": student.monthly_fee,

                "food_cost": food_per_student,

                "labour_cost": labour_per_student,

                "other_cost": other_per_student,

                "absent_days": 0,

                "allowed_adjustment_days": 0,

                "food_adjustment": Decimal("0.00"),

                "final_amount": student.monthly_fee,

                "paid_amount": Decimal("0.00"),

                "balance": student.monthly_fee,

                "extra_paid": Decimal("0.00"),

                "credit_used": Decimal("0.00"),
            }
        )

        if created:

            created_count += 1

        else:

            existing_count += 1

        # ====================================================
        # ALWAYS UPDATE MONTHLY EXPENSE SHARE
        # ====================================================

        bill.monthly_fee = student.monthly_fee

        bill.food_cost = food_per_student

        bill.labour_cost = labour_per_student

        bill.other_cost = other_per_student

        # ====================================================
        # ACTUAL FULL ABSENT DAYS FROM MEAL ATTENDANCE
        # ====================================================
        bill.absent_days = get_month_absent_days(student, month_date)

        # ====================================================
        # ACTUAL PAYMENT
        # ====================================================

        paid_amount = get_paid_amount(
            student,
            month_date
        )

        bill.paid_amount = money(
            paid_amount
        )

        # ====================================================
        # FINAL AMOUNT
        # ====================================================

        # If adjustment has NOT been applied,
        # final amount should be monthly fee.

        if bill.food_adjustment <= Decimal("0.00"):

            bill.final_amount = money(
                bill.monthly_fee
            )

        # ====================================================
        # BALANCE BEFORE PREVIOUS CREDIT
        # ====================================================

        balance = (

            bill.final_amount
            - bill.paid_amount

        ).quantize(
            Decimal("0.01")
        )

        if balance < Decimal("0.00"):

            balance = Decimal("0.00")

        bill.balance = balance

        # ====================================================
        # EXTRA PAYMENT
        # ====================================================

        gross_amount = get_bill_gross_amount(
            bill
        )

        extra_paid = (

            bill.paid_amount
            - gross_amount

        ).quantize(
            Decimal("0.01")
        )

        if extra_paid < Decimal("0.00"):

            extra_paid = Decimal("0.00")

        bill.extra_paid = extra_paid

        # ====================================================
        # SAVE
        # ====================================================

        bill.save(
            update_fields=[

                "monthly_fee",

                "food_cost",

                "labour_cost",

                "other_cost",

                "absent_days",

                "paid_amount",

                "final_amount",

                "balance",

                "extra_paid",
            ]
        )

        # ====================================================
        # APPLY PREVIOUS MONTH CREDIT
        # ====================================================

        apply_available_credits(
            student,
            bill
        )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    messages.success(
        request,
        f"{created_count} monthly bills generated successfully. "
        f"{existing_count} bills already existed."
    )

    return redirect(
        f"{reverse('monthly_bill_list')}"
        f"?month={selected_month}"
    )


# ============================================================
# USE CREDIT
# ============================================================

@admin_required
@transaction.atomic
def use_credit(request, id):

    """
    Manual credit application endpoint.

    Usually previous-month credits are automatically applied
    during monthly bill generation.
    """

    if request.method != "POST":

        return redirect(
            "monthly_bill_list"
        )

    bill = get_object_or_404(
        MonthlyBill,
        id=id
    )

    apply_available_credits(
        bill.student,
        bill
    )

    messages.success(
        request,
        "Available previous credit applied successfully."
    )

    return redirect(
        f"{reverse('monthly_bill_list')}"
        f"?month={bill.month.strftime('%Y-%m')}"
    )


# ============================================================
# REFUND CREDIT URL COMPATIBILITY
# ============================================================

@admin_required
def refund_credit(request, id):

    """
    Compatibility wrapper for existing URL name.
    """

    return process_credit_refund(
        request,
        id
    )
# ============================================================
# CREDIT EXTRA PAYMENT TO NEXT MONTH
# ============================================================

@admin_required
@transaction.atomic
def next_month_credit(request, id):

    if request.method != "POST":
        return redirect("monthly_bill_list")

    bill = get_object_or_404(
        MonthlyBill.objects.select_related("student"),
        id=id
    )

    # --------------------------------------------------------
    # GET ACTUAL PAID AMOUNT
    # --------------------------------------------------------

    paid_amount = FeePayment.objects.filter(
        student=bill.student,
        month=bill.month,
        status="Paid"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    bill.paid_amount = paid_amount

    # --------------------------------------------------------
    # CALCULATE CURRENT MONTH EXTRA
    # --------------------------------------------------------
    #
    # IMPORTANT:
    # final_amount may already have been reduced by a previous
    # month's credit. That reduction is NOT a new extra payment.
    # Therefore calculate extra against the gross bill amount.
    # --------------------------------------------------------

    extra_amount = get_bill_extra_amount(
        bill
    )

    if extra_amount <= Decimal("0.00"):

        messages.error(
            request,
            "There is no extra payment available for credit."
        )

        return redirect(
            f"{reverse('monthly_bill_list')}"
            f"?month={bill.month.strftime('%Y-%m')}"
        )

    # --------------------------------------------------------
    # PREVENT DUPLICATE CREDIT
    # --------------------------------------------------------

    existing_credit = CreditRefund.objects.filter(
        source_bill=bill,
        transaction_type="Credit"
    ).exists()

    if existing_credit:

        messages.warning(
            request,
            "Credit for this bill has already been processed."
        )

        return redirect(
            f"{reverse('monthly_bill_list')}"
            f"?month={bill.month.strftime('%Y-%m')}"
        )

    # --------------------------------------------------------
    # CREATE CREDIT
    # --------------------------------------------------------

    CreditRefund.objects.create(

        source_bill=bill,

        student=bill.student,

        transaction_type="Credit",

        amount=extra_amount,

        used_amount=Decimal("0.00"),

        status="Available",

        processed_date=timezone.localdate(),

        note="Extra payment credited for next month's mess bill."
    )

    # --------------------------------------------------------
    # UPDATE BILL
    # --------------------------------------------------------

    bill.extra_paid = extra_amount

    bill.credit_status = "Credited"

    bill.save(
        update_fields=[
            "extra_paid",
            "credit_status",
            "paid_amount",
        ]
    )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    messages.success(
        request,
        f"₹{extra_amount} credited successfully for "
        f"{bill.student.name}'s next month bill."
    )

    return redirect(
        f"{reverse('monthly_bill_list')}"
        f"?month={bill.month.strftime('%Y-%m')}"
    )

# ============================================================
# STUDENT PORTAL
# ============================================================

def student_login(request):

    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("dashboard")
        return redirect("student_dashboard")

    if request.method == "POST":

        login_id = request.POST.get("login_id", "").strip().lower()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=login_id,
            password=password,
        )

        if user is not None and not user.is_staff and user.is_active:

            student = Student.objects.filter(
                email=user.email,
                is_active=True
            ).first()

            if student:
                login(request, user)
                return redirect("student_dashboard")

        return render(
            request,
            "mainapp/student/student_login.html",
            {"error": "Invalid email/password, or account is inactive."}
        )

    return render(request, "mainapp/student/student_login.html")


@login_required(login_url="student_login")
def student_dashboard(request):

    if request.user.is_staff:
        return redirect("dashboard")

    student = get_object_or_404(
        Student,
        email=request.user.email,
        is_active=True
    )

    selected_month = request.GET.get(
        "month",
        timezone.localdate().strftime("%Y-%m")
    ).strip()
    try:
        year, month = selected_month.split("-")
        month_date = date(int(year), int(month), 1)
    except (ValueError, TypeError):
        month_date = timezone.localdate().replace(day=1)
        selected_month = month_date.strftime("%Y-%m")

    bill = MonthlyBill.objects.filter(
        student=student,
        month=month_date
    ).first()

    if bill:
        bill.absent_days = get_month_absent_days(student, month_date)
        bill.save(update_fields=["absent_days"])
        update_bill_payment_values(bill)

    attendance = MealAttendance.objects.filter(
        student=student,
        date__year=month_date.year,
        date__month=month_date.month
    ).order_by("date")

    absent_days = get_month_absent_days(student, month_date)

    present_days = attendance.filter(
        breakfast=True,
        lunch=True,
        dinner=True
    ).count()

    payments = FeePayment.objects.filter(
        student=student
    ).order_by("-payment_date", "-id")[:10]

    credits = CreditRefund.objects.filter(
        student=student
    ).select_related("source_bill", "target_bill").order_by("-created_at")[:10]

    available_total = CreditRefund.objects.filter(
        student=student,
        transaction_type="Credit",
        status__in=["Available", "Partially Used"]
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    used_total = CreditRefund.objects.filter(
        student=student,
        transaction_type="Credit"
    ).aggregate(
        total=Sum("used_amount")
    )["total"] or Decimal("0.00")

    available_credit = money(available_total - used_total)

    return render(
        request,
        "mainapp/student/student_dashboard.html",
        {
            "student": student,
            "bill": bill,
            "selected_month": selected_month,
            "attendance": attendance,
            "absent_days": absent_days,
            "present_days": present_days,
            "payments": payments,
            "credits": credits,
            "available_credit": available_credit,
        }
    )


def student_logout(request):
    logout(request)
    return redirect("student_login")
