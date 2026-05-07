from rest_framework.throttling import ScopedRateThrottle


class LoginRateThrottle(ScopedRateThrottle):
    scope = "login"


class PasswordResetRequestRateThrottle(ScopedRateThrottle):
    scope = "password_reset_request"


class PasswordResetVerifyRateThrottle(ScopedRateThrottle):
    scope = "password_reset_verify"


class PublicRegistrationRateThrottle(ScopedRateThrottle):
    scope = "public_registration"
