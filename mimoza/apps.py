from django.apps import AppConfig


class MimozaConfig(AppConfig):
    name = 'mimoza'

    def ready(self):
        from . import audit
        from . import mobile_notifications
