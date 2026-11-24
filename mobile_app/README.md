# Mimoza Floral mobile app

Flutter mobile client for the Mimoza Django storefront. The app has five
bottom-navigation sections: home, catalog, Reels, cart, and profile. The live
catalog, category filtering, search, product details, and stock-limited
in-memory cart are connected. The profile supports customer sign-in and
registration, stores the expiring access token in platform secure storage, and
shows the customer's latest 20 orders with their status, five-digit code,
items, date, and total. Reels displays in-stock products with videos in a
vertical feed. Uploaded videos and HLS playlists play in the app; external
links ending in `.m3u8`, `.mp4`, `.m4v`, `.webm`, or `.mov` are also played
in the app. Other external links open in the device's browser or compatible app.
The feed is shuffled for each refresh and keeps a stable order between pages.
Customers can like and unlike Reels after signing in; likes are shared with the
website's product likes.

## Run against the local Django server

From the project root, allow the Android emulator host and start Django:

```powershell
$env:DJANGO_ALLOWED_HOSTS = '127.0.0.1,localhost,10.0.2.2'
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

In another terminal:

```powershell
Set-Location .\mobile_app
flutter run
```

The Android emulator reaches the development host at `10.0.2.2`. For a physical
device, set `API_BASE_URL` to the computer's LAN address and allow that address
in Django's `DJANGO_ALLOWED_HOSTS`.

## Build for a deployed server

Use the site's HTTPS origin when building a release APK:

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://your-domain.example
```

The app reads products from `/api/v1/products/` and
`/api/v1/products/<slug>/`. Customer account endpoints are
`/api/v1/auth/register/`, `/api/v1/auth/login/`, `/api/v1/auth/logout/`, and
`/api/v1/account/`. The video feed reads pages from `/api/v1/reels/`. Access
tokens expire after 30 days and are stored hashed on
the server; changing the account password invalidates existing tokens.

The cart is local to the app session. Checkout supports Click and Payme hosted
payment when the corresponding credentials and callbacks are configured on the
server. It opens the provider checkout outside the app; the server alone marks
the 30% advance as paid after an authenticated provider callback. The remaining
70% is due on delivery or collection. Uzum remains disabled until its callback
verification procedure is confirmed. Never place payment credentials in the
mobile app or Django admin's legacy API-key fields. Live verification requires
merchant accounts and provider sandbox credentials. Existing orders can still
be reopened, and their delivery requests link to Telegram.

## Mobile push notifications

The app can register a signed-in device for Firebase Cloud Messaging (FCM).
Customers receive order/payment status updates and important-date reminders;
super admins and active managers receive notifications for accepted orders
(online orders only after payment confirmation). Notifications contain no
customer contact details. Registration is removed when logout succeeds.
Foreground notifications appear in the app on Android and as system banners
on iOS. Notification taps open the app.

Push is disabled unless `FIREBASE_ENABLED=true` is supplied at build time.
Create a Firebase project and register the Android app
`uz.mimoza.floral.mimoza_mobile` and iOS app
`uz.mimoza.floral.mimozaMobile`. Put Android's `google-services.json` in
`mobile_app/android/app/`; the file is ignored by Git. For each platform build,
use that Firebase app's values (not a service-account key) as Dart defines:

```bash
flutter build apk --dart-define=API_BASE_URL=https://your-domain.example \
  --dart-define=FIREBASE_ENABLED=true \
  --dart-define=FIREBASE_API_KEY=YOUR_API_KEY \
  --dart-define=FIREBASE_APP_ID=YOUR_ANDROID_APP_ID \
  --dart-define=FIREBASE_SENDER_ID=YOUR_SENDER_ID \
  --dart-define=FIREBASE_PROJECT_ID=YOUR_PROJECT_ID
```

For iOS, use `flutter build ipa` with the iOS app's API key and app ID and
add `--dart-define=FIREBASE_IOS_BUNDLE_ID=uz.mimoza.floral.mimozaMobile`.
The Codemagic unsigned workflow does not provide these settings and does not
enable push. Set up Apple Push Notifications capability, an appropriate signing
profile and an APNs authentication key uploaded to Firebase before testing on
an iPhone. The iOS build must also use the deployed HTTPS `API_BASE_URL`.
Firebase service-account credentials must remain on the server, not in the app.
See the mobile push section of `MEDIA_AND_NOTIFICATIONS.md` for server setup.
Real delivery must be tested on devices after Firebase and APNs are configured.

Super admins and active managers see a native CRM dashboard after sign-in.
The storefront navigation remains available, and an Admin tab returns to the
dashboard.
They can search orders, update their status and assigned workers, manage
products and stock (including image and video uploads), and view analytics.
Super admins can also view staff, change their roles, and inspect audit history.
Staff accounts and categories must still be created on the website. Other staff
roles do not gain access to the native dashboard. Product edits are rejected
if the product changed since it was opened; return to the list and reopen it.

## iOS preparation

The iOS project has built unsigned in Codemagic, but has not been tested on an
iPhone. Building for iOS requires macOS and Xcode, locally or through Codemagic.
On a Mac, install Flutter and Xcode, run `flutter pub get`, then open
`ios/Runner.xcworkspace` in Xcode and select a signing team and a unique bundle
identifier for a physical device. The generated bundle ID is provisional.
An Apple account can be used for development signing; App Store distribution
requires Apple Developer Program membership.

For Sideloadly testing, run the `ios-sideload-release` Codemagic workflow.
Download `Mimoza-unsigned.ipa` from its artifacts and use Sideloadly to sign and
install it on the iPhone. The IPA is unsigned until Sideloadly signs it; it is
not an App Store or TestFlight build. A debug iOS build cannot be launched from
the home screen on iOS 14 or newer. Do not share Apple credentials or signing
keys in chat.

The Sideloadly workflow sets `API_BASE_URL` in `environment.vars` to
`https://mimozafloral.uz`. The server must have the mobile API deployed for
server-dependent features to work. If the server address changes, update the
workflow and build and install a new IPA. The address must be an HTTPS origin.

Run with the deployed HTTPS server origin, for example:

```bash
flutter run --dart-define=API_BASE_URL=https://your-domain.example
```

The default API address is for the Android emulator. On iOS an explicit
`API_BASE_URL` is required; the app reports an error if it is missing.
Use HTTPS for the API and product media: iOS App Transport Security is not
weakened for local HTTP. The iOS app icons use the existing Mimoza logo.
Verify sign-in/keychain persistence, photo/video
selection, Reels playback, checkout, and admin management on an actual iPhone
before distribution. Prefer MP4 or HLS for Reels; other video formats supported
on Android are not guaranteed to play on iOS.
