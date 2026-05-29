from django.test import TestCase
from rest_framework.test import APIClient

from .models import PasswordResetOTP, User, UserRole, VerificationStatus


class AccountSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def _set_csrf(self):
        response = self.client.get("/api/accounts/auth/csrf/")
        return response.cookies["csrftoken"].value

    def test_csrf_endpoint_returns_token_for_cross_subdomain_frontends(self):
        response = self.client.get("/api/accounts/auth/csrf/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        self.assertTrue(response.data["csrfToken"])

    def test_existing_user_cannot_be_overwritten_by_public_registration(self):
        user = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            role=UserRole.ADMIN,
            is_active=True,
            verification_status=VerificationStatus.APPROVED,
        )
        csrf = self._set_csrf()
        response = self.client.post(
            "/api/accounts/public/register/landlord/",
            {
                "fullName": "Attacker",
                "email": user.email,
                "phone": "9999999999",
                "propertyAddress": "Test address",
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        user.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(user.role, UserRole.ADMIN)
        self.assertTrue(user.is_active)
        self.assertEqual(user.verification_status, VerificationStatus.APPROVED)

    def test_login_requires_csrf(self):
        response = self.client.post(
            "/api/accounts/auth/login/",
            {"email": "user@example.com", "password": "test"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_password_reset_otp_is_hashed_and_limited(self):
        user = User.objects.create_user(
            email="user@example.com",
            password="OldPass123!",
            is_active=True,
            verification_status=VerificationStatus.APPROVED,
        )
        otp = PasswordResetOTP.generate_otp()
        record = PasswordResetOTP.create_for_user(user=user, otp=otp)
        self.assertNotEqual(record.otp_hash, otp)
        self.assertTrue(record.verify(otp))

        csrf = self._set_csrf()
        for _ in range(5):
            response = self.client.post(
                "/api/accounts/auth/password/otp/verify/",
                {"email": user.email, "otp": "000000", "new_password": "NewPass123!"},
                format="json",
                HTTP_X_CSRFTOKEN=csrf,
            )
            self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/accounts/auth/password/otp/verify/",
            {"email": user.email, "otp": otp, "new_password": "NewPass123!"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 429)
