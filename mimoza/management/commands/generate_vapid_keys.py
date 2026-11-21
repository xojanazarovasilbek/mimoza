import base64

from cryptography.hazmat.primitives.serialization import NoEncryption, PrivateFormat, Encoding, PublicFormat
from django.core.management.base import BaseCommand
from py_vapid import Vapid


class Command(BaseCommand):
    help = 'Generate Web Push VAPID keys for environment configuration.'

    def handle(self, *args, **options):
        vapid = Vapid()
        vapid.generate_keys()
        private_der = vapid.private_key.private_bytes(
            Encoding.DER,
            PrivateFormat.PKCS8,
            NoEncryption(),
        )
        public_key = vapid.public_key.public_bytes(
            Encoding.X962,
            PublicFormat.UncompressedPoint,
        )
        self.stdout.write('Keep the private key secret; do not commit it or send it in chat.')
        public_key_b64 = base64.urlsafe_b64encode(public_key).rstrip(b'=').decode('ascii')
        private_key_b64 = base64.urlsafe_b64encode(private_der).rstrip(b'=').decode('ascii')
        self.stdout.write(f'WEBPUSH_VAPID_PUBLIC_KEY={public_key_b64}')
        self.stdout.write(f'WEBPUSH_VAPID_PRIVATE_KEY={private_key_b64}')
        self.stdout.write('WEBPUSH_VAPID_SUBJECT=mailto:your-contact-email')
