# Deployment Notes

## Local
1. Copy `.env.example` to `.env`.
2. Fill in SECRET_KEY and Gmail App Password.
3. Install requirements: `pip install -r requirements.txt`
4. Run migrations: `python manage.py migrate`
5. Run: `python manage.py runserver`

## Render
Recommended production database: PostgreSQL.
Set these environment variables in Render:
- SECRET_KEY
- DEBUG=False
- ALLOWED_HOSTS=your-app.onrender.com
- CSRF_TRUSTED_ORIGINS=https://your-app.onrender.com
- TIME_ZONE=Asia/Kolkata
- DATABASE_URL=<Render PostgreSQL Internal Database URL>
- EMAIL_HOST=smtp.gmail.com
- EMAIL_PORT=587
- EMAIL_USE_TLS=True
- EMAIL_HOST_USER=<Gmail address>
- EMAIL_HOST_PASSWORD=<Gmail App Password>
- DEFAULT_FROM_EMAIL=<Gmail address>
- EMAIL_TIMEOUT=10

Build command: `./build.sh`
Start command: `gunicorn MMS.wsgi:application`

The real `.env` and local SQLite database are intentionally not included in this deployment package.
