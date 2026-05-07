from django.test import TestCase
from rest_framework.test import APIClient


class ContactSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def test_contact_create_requires_csrf(self):
        response = self.client.post(
            "/api/core/contact/public/",
            {
                "name": "Test",
                "email": "test@example.com",
                "subject": "Hello",
                "contact_type": "student",
                "message": "World",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
