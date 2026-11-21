# Media and notification setup

## Linux VPS deployment

The application is configured for Gunicorn behind an HTTPS reverse proxy such as
Nginx, with PostgreSQL in production. Copy `.env.example` values to
`/etc/mimoza/mimoza.env`; protect that file so only the service administrator
can read it. Generate `DJANGO_SECRET_KEY` on the server with:

```bash
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set the real domain in `DJANGO_ALLOWED_HOSTS` and matching HTTPS origins in
`DJANGO_CSRF_TRUSTED_ORIGINS`. The reverse proxy must overwrite
`X-Forwarded-Proto` with the actual scheme. Keep `DJANGO_HSTS_SECONDS=0` until
HTTPS is verified, then enable HSTS. Never use the development SQLite database
for production.

Install Python dependencies and FFmpeg, create the PostgreSQL database, and
create the service environment file with permissions `600`.

If the existing SQLite database has products, orders, or customer data, export
it on the source machine (PowerShell), then transfer the fixture securely:

```powershell
.\.venv\Scripts\python.exe manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --output production-data.json
```

Treat that fixture as sensitive customer data and remove it after import. Copy
any existing `media/` files to the server and sync them to the R2 bucket root so
database file paths continue to resolve:

```bash
aws s3 sync /path/to/old-media/ s3://BUCKET/ --endpoint-url https://ACCOUNT_ID.r2.cloudflarestorage.com
```

After transferring any fixture and media, run from the application folder on the
server:

```bash
.venv/bin/python manage.py migrate --noinput
# Only when importing existing data:
.venv/bin/python manage.py loaddata production-data.json
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check --deploy
```

Copy `deploy/mimoza.service`, `deploy/mimoza-reminders.service`, and
`deploy/mimoza-reminders.timer` to `/etc/systemd/system/`, adjusting the
application path and service user if needed. Then run `systemctl daemon-reload`,
`systemctl enable --now mimoza mimoza-reminders.timer`, and configure the HTTPS
reverse proxy to send requests to `127.0.0.1:8000`; adapt
`deploy/nginx.conf.example` for the domain and certificate paths. It forwards
the HTTPS scheme header Django requires. The reminder timer runs at 04:00 UTC
(09:00 in Tashkent). Configure firewall rules so the Gunicorn port is not
exposed publicly. Production email uses SMTP; configure `EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and TLS settings if the
server does not provide a local mail relay. After HTTPS is confirmed, set
`DJANGO_HSTS_SECONDS=31536000`. Enable `DJANGO_HSTS_INCLUDE_SUBDOMAINS` and
`DJANGO_HSTS_PRELOAD` only if every subdomain is HTTPS-only and you intend to
request browser preload inclusion.

## Web Push

Generate a VAPID key pair locally:

```powershell
python manage.py generate_vapid_keys
```

Keep `WEBPUSH_VAPID_PRIVATE_KEY` secret. Configure the printed public key, private
key, and a valid `WEBPUSH_VAPID_SUBJECT` (`mailto:...` or an HTTPS contact URL) as
environment variables. Push subscriptions require HTTPS in production; localhost
is suitable for development.

Run `python manage.py send_important_date_reminders` once per day. Schedule it
with the deployment platform's scheduler or Windows Task Scheduler. It sends
annual-date reminders two days in advance, and records the occurrence only after
at least one browser receives the push.

## Cloudflare R2

Create an R2 bucket, an access key limited to that bucket, and a public custom
domain for media. Set `R2_STORAGE_ENABLED=true` and provide `R2_ACCOUNT_ID`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, and
`R2_PUBLIC_DOMAIN` through the deployment environment. Do not commit credentials.
The R2 domain must serve uploaded objects over HTTPS. Configure its CORS policy
to allow GET/HEAD from the storefront's origin so browsers can load images, HLS
playlists, and segments.

When R2 is disabled, uploaded media is stored under the local `media/` directory.
Uploaded product and story images are converted to WebP automatically.

## HLS video

Install FFmpeg on the server and make its executable available as `ffmpeg`, or
set `FFMPEG_BINARY` to its path. After uploading a product or Story video, run:

```powershell
python manage.py transcode_video_hls product PRODUCT_ID
python manage.py transcode_video_hls story STORY_ID
```

The command creates a VOD HLS playlist and segments in the configured media
storage and associates the playlist with the product. With R2 enabled, the files
are served through the configured public media domain. Browsers with native HLS
support use the playlist; others can use the uploaded video source.
