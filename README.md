# Hostel Mess Management System - Final Updated Version

## Included
- Professional admin dashboard and responsive UI
- Student management
- Automatic Student Portal account when a new student is added from Admin
- Student Login ID = Student email address
- Initial password = Student ID / Roll No.
- Credentials email sent only to that student's registered email
- Admin Login / Reset credentials for existing students
- Strict admin-only access for management pages
- Student portal can view only the logged-in student's own profile, attendance, bills, payments and credit/refund history
- Monthly bills
- Full absent-day calculation from MealAttendance
- Food adjustment
- Fee payments
- Automatic fee-payment email notification to the same student's email
- Credit / refund and next-month credit
- Food, labour and other expenses
- Attendance
- Professional footer with Shreyansh Upadhyay

## Attendance rule
A monthly absent day is counted when a MealAttendance record for that date has:
- breakfast = False
- lunch = False
- dinner = False

A missing attendance record is not silently counted as an absent day.

## Student login and email
When Admin adds a student:
1. Student is saved.
2. A Django user account is created automatically.
3. Username/login ID = the student's email address.
4. Initial password = the student's Student ID / Roll No.
5. Credentials are emailed only to that student's registered email.
6. The admin also receives an on-screen result showing whether the email was sent.

For older students already present in the database, use Login / Reset from the Students page to create/reset their portal credentials.

## Fee payment email
When Admin records a fee payment:
- The payment is saved with its receipt number.
- A payment confirmation/notification is sent only to the email address of the student attached to that payment.
- The email includes receipt number, month, amount, payment date, payment method, status, total paid for that month, and current bill balance when a monthly bill exists.
- Editing a payment also sends an updated-payment notification to that same student's email.

If email sending fails, the payment is still saved and the admin sees the email error instead of losing the payment.

## Gmail SMTP
The application reads SMTP settings from environment variables using python-dotenv.

Create a `.env` file in the same folder as `manage.py` using `.env.example` as the template.

Required values:
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD` (use a Gmail App Password, not your normal Gmail password)
- `DEFAULT_FROM_EMAIL`

Never upload `.env` to GitHub.

## Run
```bash
pip install -r requirements.txt
python manage.py runserver
```

Admin login:
- `/login/`

Student login:
- `/student/login/`
