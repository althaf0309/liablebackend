from rest_framework.throttling import ScopedRateThrottle


class ContactCreateRateThrottle(ScopedRateThrottle):
    scope = "contact_create"
