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

## Online payments, order QR codes, and staff access

Website and mobile checkout support Click Shop API and Payme hosted checkout
when their server environment credentials are configured. The customer pays
30% online; the remaining 70% is due at delivery or collection. Orders reserve
inventory during the payment window; run
`python manage.py expire_pending_payments` on a recurring schedule (for example,
every five minutes) so expired payments release that reservation.

Set `CLICK_MERCHANT_ID`, `CLICK_SERVICE_ID`, and `CLICK_SECRET_KEY` in the
protected server environment. Configure Click's Prepare and Complete callbacks
to `https://<your-domain>/payment/click/callback/`.
Set `PAYME_MERCHANT_ID`, `PAYME_MERCHANT_LOGIN`, and `PAYME_MERCHANT_KEY` in the
same protected environment; `PAYME_ACCOUNT_FIELD` must match the order-ID field
configured on the Payme cash register (defaults to `order_id`). Configure the
Payme cash register callback as
`https://<your-domain>/payment/payme/callback/`.
Payme checkout links are requested server-to-server from its signed
`/api/checkout/url` endpoint; the app never receives merchant secrets.

The old API-key fields in Django admin are not used; never put provider secrets
in them or in the mobile app. Uzum checkout is deliberately not offered until
Uzum confirms an authenticated callback-verification procedure. Setting an
Uzum key alone does not enable it. Mocked local tests do not replace provider
sandbox verification; real checkout needs approved merchant accounts and
credentials.

Paid orders remain available in the customer account and can be marked for
delivery or store collection. QR codes and staff access continue to work as
before.

After an order is accepted, the customer receives a QR code containing an
opaque order reference, not their contact details. The customer chooses pickup
or delivery on the confirmation page; for delivery, the Telegram link prepares
the order reference, product IDs, name, and phone so the customer can send them
along with their live location. The customer's account keeps a private QR-code
link for each order.

Super Admins can assign the **Do‘konchi** role in CRM user management. This role
can search orders by QR reference, order number, customer name, or phone and
flower ID/name, and advance an order through its valid statuses. It cannot
access the dashboard, inventory, analytics, staff management, or order
financial totals. Apply Django migrations on deployment before enabling this
workflow.

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

## Mobile Push (Firebase)

Create a Firebase project and configure the Android and iOS apps as described
in `mobile_app/README.md`. Enable Firebase Cloud Messaging and upload an Apple
Push Notifications authentication key to Firebase for iOS. Provision the
app's push entitlement in the Apple Developer portal and signing profile.
Firebase setup files and service-account keys must not be sent in chat.

On the server, install the updated requirements, run `python manage.py migrate`,
and set `GOOGLE_APPLICATION_CREDENTIALS` to the absolute path of a protected
Firebase service-account JSON file for the same project. Keep the file outside
the repository and readable only by the service account. Alternatively use
Google Application Default Credentials when available.

Install `deploy/mimoza-mobile-push.service` and
`deploy/mimoza-mobile-push.timer`, adjust the application path and user, and
enable the timer with `systemctl enable --now mimoza-mobile-push.timer` after
`systemctl daemon-reload`. It queues important-date reminders and sends pending
messages every minute. A delivery error leaves the message queued for retry and
is reported in the service logs. Firebase acceptance is not a guarantee of
device delivery. Customers and admins must sign in and allow notifications.
Web and mobile reminder delivery are tracked independently.

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
