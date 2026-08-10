"""
URL configuration for MMS project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""



from django.contrib import admin
from django.urls import path

from mainapp import views


urlpatterns = [

    # =========================================================
    # DJANGO ADMIN
    # =========================================================

    path(
        "django-admin/",
        admin.site.urls
    ),


    # =========================================================
    # ADMIN LOGIN / LOGOUT
    # =========================================================

    path(
        "",
        views.admin_login,
        name="admin_login"
    ),

    path(
        "login/",
        views.admin_login,
        name="admin_login"
    ),

    path(
        "logout/",
        views.admin_logout,
        name="admin_logout"
    ),



    # =========================================================
    # STUDENT PORTAL
    # =========================================================

    path(
        "student/login/",
        views.student_login,
        name="student_login"
    ),

    path(
        "student/dashboard/",
        views.student_dashboard,
        name="student_dashboard"
    ),

    path(
        "student/logout/",
        views.student_logout,
        name="student_logout"
    ),

    # =========================================================
    # DASHBOARD
    # =========================================================

    path(
        "dashboard/",
        views.dashboard,
        name="dashboard"
    ),


    # =========================================================
    # STUDENTS
    # =========================================================

    path(
        "students/",
        views.student_list,
        name="student_list"
    ),

    path(
        "students/add/",
        views.student_add,
        name="student_add"
    ),

    path(
        "students/edit/<int:id>/",
        views.student_edit,
        name="student_edit"
    ),

    path(
        "students/toggle/<int:id>/",
        views.student_toggle_status,
        name="student_toggle_status"
    ),

    path(
        "students/credentials/<int:id>/",
        views.student_credentials,
        name="student_credentials"
    ),


    # =========================================================
    # FEE PAYMENTS
    # =========================================================

    path(
        "fees/",
        views.fee_list,
        name="fee_list"
    ),

    path(
        "fees/add/",
        views.fee_add,
        name="fee_add"
    ),

    path(
        "fees/edit/<int:id>/",
        views.fee_edit,
        name="fee_edit"
    ),


    # =========================================================
    # ATTENDANCE
    # =========================================================

    path(
        "attendance/",
        views.attendance,
        name="attendance"
    ),


    # =========================================================
    # EXPENSES
    # =========================================================

    path(
        "expenses/",
        views.expense_list,
        name="expense_list"
    ),

    path(
        "expenses/add/",
        views.expense_add,
        name="expense_add"
    ),

    path(
        "expenses/edit/<int:id>/",
        views.expense_edit,
        name="expense_edit"
    ),


    # =========================================================
    # MESS VACATION
    # =========================================================

    path(
        "vacations/",
        views.vacation_list,
        name="vacation_list"
    ),

    path(
        "vacations/add/",
        views.vacation_add,
        name="vacation_add"
    ),

    path(
        "vacations/delete/<int:id>/",
        views.vacation_delete,
        name="vacation_delete"
    ),


    # =========================================================
    # MONTHLY BILLS
    # =========================================================

    path(
        "monthly-bills/",
        views.monthly_bill_list,
        name="monthly_bill_list"
    ),

    path(
        "monthly-bills/generate/",
        views.generate_monthly_bills,
        name="generate_monthly_bills"
    ),

    path(
        "monthly-bills/apply-adjustment/<int:id>/",
        views.apply_food_adjustment,
        name="apply_food_adjustment"
    ),


    # =========================================================
    # CREDIT / REFUND SYSTEM
    # =========================================================

    path(
        "refund-credit/<int:id>/",
        views.process_credit_refund,
        name="refund_credit"
    ),

    path(
        "monthly-bills/use-credit/<int:id>/",
        views.use_credit,
        name="use_credit"
    ),

    path(
        "monthly-bills/next-month-credit/<int:id>/",
        views.next_month_credit,
        name="next_month_credit"
    ),

]

