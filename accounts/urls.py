from django.urls import path

from .admin_api import *
from .views import *


urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/password/otp/request/", ForgotPasswordOTPRequestView.as_view(), name="otp-request"),
    path("auth/password/otp/verify/", ForgotPasswordOTPVerifyView.as_view(), name="otp-verify"),
    path("public/register/landlord/", PublicRegisterLandlordView.as_view(), name="public-register-landlord"),
    path("public/register/student/", PublicRegisterStudentView.as_view(), name="public-register-student"),
    path("public/questions/", PublicQuestionsView.as_view(), name="public-questions"),
    path("answers/", AnswerUpsertView.as_view(), name="answers-upsert"),
    path("users/", AdminUserListCreateView.as_view(), name="admin-user-list-create"),
    path("users/<uuid:id>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
]
