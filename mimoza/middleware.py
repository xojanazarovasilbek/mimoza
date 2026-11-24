from .audit import reset_audit_actor, set_audit_actor


class AuditActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        actor = user if user is not None and user.is_authenticated else None
        token = set_audit_actor(actor)
        try:
            return self.get_response(request)
        finally:
            reset_audit_actor(token)
