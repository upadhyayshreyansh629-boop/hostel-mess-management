
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


# =========================================================
# STUDENT
# =========================================================

class Student(models.Model):

    YEAR_CHOICES = [
        ("1st Year", "1st Year"),
        ("2nd Year", "2nd Year"),
        ("3rd Year", "3rd Year"),
    ]

    name = models.CharField(
        max_length=100
    )

    student_id = models.CharField(
        max_length=50,
        unique=True
    )

    year = models.CharField(
        max_length=20,
        choices=YEAR_CHOICES
    )

    branch = models.CharField(
        max_length=100,
        blank=True
    )

    room_no = models.CharField(
        max_length=20,
        blank=True
    )

    email = models.EmailField(
        unique=True
    )

    mobile = models.CharField(
        max_length=15,
        blank=True
    )

    mess_joining_date = models.DateField()

    mess_leaving_date = models.DateField(
        null=True,
        blank=True
    )

    monthly_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=2500
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.name} - {self.student_id}"


# =========================================================
# FEE PAYMENT
# =========================================================

class FeePayment(models.Model):

    PAYMENT_STATUS = [
        ("Paid", "Paid"),
        ("Partial", "Partial"),
        ("Pending", "Pending"),
    ]

    PAYMENT_METHODS = [
        ("Cash", "Cash"),
        ("UPI", "UPI"),
        ("Bank Transfer", "Bank Transfer"),
        ("Other", "Other"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="fee_payments"
    )

    month = models.DateField()

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(
                Decimal("0")
            )
        ]
    )

    payment_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default="Paid"
    )

    payment_method = models.CharField(
        max_length=30,
        choices=PAYMENT_METHODS,
        default="Cash"
    )

    receipt_no = models.CharField(
        max_length=50,
        unique=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.student.name} - ₹{self.amount}"


# =========================================================
# MEAL ATTENDANCE
# =========================================================

class MealAttendance(models.Model):

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="meal_attendance"
    )

    date = models.DateField()

    breakfast = models.BooleanField(
        default=False
    )

    lunch = models.BooleanField(
        default=False
    )

    dinner = models.BooleanField(
        default=False
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student",
                    "date"
                ],
                name="unique_student_attendance_date"
            )
        ]

    def __str__(self):
        return f"{self.student.name} - {self.date}"


# =========================================================
# EXPENSE
# =========================================================

class Expense(models.Model):

    EXPENSE_TYPES = [
        ("Food", "Food / Saman"),
        ("Labour", "Labour"),
        ("Other", "Other"),
    ]

    expense_type = models.CharField(
        max_length=20,
        choices=EXPENSE_TYPES
    )

    item_name = models.CharField(
        max_length=150
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(
                Decimal("0")
            )
        ]
    )

    expense_date = models.DateField()

    description = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.item_name} - ₹{self.amount}"


# =========================================================
# MESS VACATION
# =========================================================

class MessVacation(models.Model):

    start_date = models.DateField()

    end_date = models.DateField()

    reason = models.CharField(
        max_length=200
    )

    mess_closed = models.BooleanField(
        default=True
    )

    description = models.TextField(
        blank=True
    )

    def __str__(self):
        return f"{self.start_date} to {self.end_date}"


# =========================================================
# MONTHLY BILL
# =========================================================

class MonthlyBill(models.Model):

    # -----------------------------------------------------
    # CREDIT STATUS
    # -----------------------------------------------------

    CREDIT_STATUS = [
        ("None", "None"),
        ("Pending", "Pending"),
        ("Refunded", "Refunded"),
        ("Credited", "Credited"),
        ("Used", "Used"),
    ]

    # -----------------------------------------------------
    # STUDENT / MONTH
    # -----------------------------------------------------

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="monthly_bills"
    )

    month = models.DateField()

    # -----------------------------------------------------
    # BASIC BILL DETAILS
    # -----------------------------------------------------

    monthly_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    food_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    labour_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    other_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # -----------------------------------------------------
    # ATTENDANCE / ADJUSTMENT
    # -----------------------------------------------------

    absent_days = models.PositiveIntegerField(
        default=0
    )

    allowed_adjustment_days = models.PositiveIntegerField(
        default=0
    )

    food_adjustment = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # -----------------------------------------------------
    # FINAL BILL
    # -----------------------------------------------------

    final_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # -----------------------------------------------------
    # PAYMENT
    # -----------------------------------------------------

    paid_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # -----------------------------------------------------
    # BALANCE
    # -----------------------------------------------------

    balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # -----------------------------------------------------
    # EXTRA PAID / CREDIT
    # -----------------------------------------------------

    extra_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    credit_status = models.CharField(
        max_length=20,
        choices=CREDIT_STATUS,
        default="None"
    )

    # -----------------------------------------------------
    # CREDIT USED FROM PREVIOUS MONTH
    # -----------------------------------------------------

    credit_used = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # -----------------------------------------------------
    # REFUND INFORMATION
    # -----------------------------------------------------

    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    refund_date = models.DateField(
        null=True,
        blank=True
    )

    # -----------------------------------------------------
    # TIMESTAMP
    # -----------------------------------------------------

    generated_at = models.DateTimeField(
        auto_now_add=True
    )

    # -----------------------------------------------------
    # UNIQUE BILL PER STUDENT / MONTH
    # -----------------------------------------------------

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student",
                    "month"
                ],
                name="unique_student_monthly_bill"
            )
        ]

    # -----------------------------------------------------
    # STRING REPRESENTATION
    # -----------------------------------------------------

    def __str__(self):

        return (
            f"{self.student.name} - "
            f"{self.month.strftime('%B %Y')}"
        )


# =========================================================
# CREDIT / REFUND
# =========================================================

class CreditRefund(models.Model):

    # -----------------------------------------------------
    # TRANSACTION TYPE
    # -----------------------------------------------------

    TRANSACTION_TYPES = [
        ("Credit", "Credit"),
        ("Refund", "Refund"),
    ]

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    STATUS_CHOICES = [
        ("Available", "Available"),
        ("Partially Used", "Partially Used"),
        ("Used", "Used"),
        ("Completed", "Completed"),
    ]

    # -----------------------------------------------------
    # SOURCE BILL
    # -----------------------------------------------------

    source_bill = models.ForeignKey(
        MonthlyBill,
        on_delete=models.CASCADE,
        related_name="credit_refunds"
    )

    # -----------------------------------------------------
    # TARGET BILL
    # -----------------------------------------------------

    target_bill = models.ForeignKey(
        MonthlyBill,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_credits"
    )

    # -----------------------------------------------------
    # STUDENT
    # -----------------------------------------------------

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="credit_refunds"
    )

    # -----------------------------------------------------
    # TRANSACTION TYPE
    # -----------------------------------------------------

    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES
    )

    # -----------------------------------------------------
    # AMOUNT
    # -----------------------------------------------------

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(
                Decimal("0")
            )
        ]
    )

    # -----------------------------------------------------
    # USED AMOUNT
    # -----------------------------------------------------

    used_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(
                Decimal("0")
            )
        ]
    )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES
    )

    # -----------------------------------------------------
    # PROCESSED DATE
    # -----------------------------------------------------

    processed_date = models.DateField(
        null=True,
        blank=True
    )

    # -----------------------------------------------------
    # NOTE
    # -----------------------------------------------------

    note = models.TextField(
        blank=True,
        null=True
    )

    # -----------------------------------------------------
    # TIMESTAMP
    # -----------------------------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    # -----------------------------------------------------
    # STRING REPRESENTATION
    # -----------------------------------------------------

    def __str__(self):

        return (
            f"{self.student.name} - "
            f"{self.transaction_type} - "
            f"₹{self.amount}"
        )

