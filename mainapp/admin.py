from django.contrib import admin
from .models import (
    Student,
    FeePayment,
    MealAttendance,
    Expense,
    MessVacation,
    MonthlyBill,
)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "student_id",
        "name",
        "year",
        "branch",
        "room_no",
        "email",
        "monthly_fee",
        "is_active",
    )

    list_filter = (
        "year",
        "branch",
        "is_active",
    )

    search_fields = (
        "name",
        "student_id",
        "email",
        "room_no",
    )


@admin.register(FeePayment)
class FeePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "month",
        "amount",
        "payment_date",
        "status",
        "receipt_no",
    )

    list_filter = (
        "status",
        "month",
    )

    search_fields = (
        "student__name",
        "student__student_id",
        "receipt_no",
    )


@admin.register(MealAttendance)
class MealAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "date",
        "breakfast",
        "lunch",
        "dinner",
    )

    list_filter = (
        "date",
        "breakfast",
        "lunch",
        "dinner",
    )

    search_fields = (
        "student__name",
        "student__student_id",
    )


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "expense_type",
        "item_name",
        "amount",
        "expense_date",
    )

    list_filter = (
        "expense_type",
        "expense_date",
    )

    search_fields = (
        "item_name",
        "description",
    )


@admin.register(MessVacation)
class MessVacationAdmin(admin.ModelAdmin):
    list_display = (
        "start_date",
        "end_date",
        "reason",
        "mess_closed",
    )

    list_filter = (
        "mess_closed",
        "start_date",
        "end_date",
    )


@admin.register(MonthlyBill)
class MonthlyBillAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "month",
        "monthly_fee",
        "food_cost",
        "labour_cost",
        "food_adjustment",
        "final_amount",
        "paid_amount",
        "balance",
    )

    list_filter = (
        "month",
    )

    search_fields = (
        "student__name",
        "student__student_id",
    )