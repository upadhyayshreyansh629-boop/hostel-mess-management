# Email Integration

1. Keep the `.env.example` file as a template.
2. Create `.env` beside `manage.py`.
3. Put your Gmail address in `EMAIL_HOST_USER` and `DEFAULT_FROM_EMAIL`.
4. Put a Gmail App Password in `EMAIL_HOST_PASSWORD`.
5. Do not use your normal Gmail password.
6. Do not commit `.env` to GitHub.

The app uses `python-dotenv` and `load_dotenv()` in settings.py.

Student-added email:
- Username = student email
- Initial password = student ID / roll number
- Credentials go only to that student's email.

Fee-payment email:
- Sent only to the student attached to the payment.
- Includes receipt/payment details and balance when a monthly bill exists.
