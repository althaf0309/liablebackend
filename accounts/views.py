from django.db import transaction
from django.utils import timezone
from django.contrib.auth import login as dj_login
from django.contrib.auth import logout as dj_logout
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.utils.decorators import method_decorator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from .models import (
    User,
    LandlordProfile,
    StudentProfile,
    Question,
    Answer,
    LoginAudit,
    UserRole,
    VerificationStatus,
    PasswordResetOTP,
)
from .serializers import (
    LandlordRegisterSerializer,
    StudentRegisterSerializer,
    QuestionSerializer,
    AnswerUpsertSerializer,
    LoginSerializer,
    UserSerializer,
    ForgotPasswordOTPRequestSerializer,
    ForgotPasswordOTPVerifySerializer,
)
from .utils import get_client_ip, get_user_agent
from .email_utils import email_send_otp
from .throttles import (
    LoginRateThrottle,
    PasswordResetRequestRateThrottle,
    PasswordResetVerifyRateThrottle,
    PublicRegistrationRateThrottle,
)


# -----------------------------
# CSRF COOKIE ENDPOINT
# -----------------------------
@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"detail": "CSRF cookie set"}, status=status.HTTP_200_OK)


# -----------------------------
# SESSION USER
# -----------------------------
class MeView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"user": UserSerializer(request.user).data}, status=status.HTTP_200_OK)


# -----------------------------
# PUBLIC REGISTER: LANDLORD
# -----------------------------
@method_decorator(csrf_protect, name="dispatch")
class PublicRegisterLandlordView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [PublicRegistrationRateThrottle]

    @transaction.atomic
    def post(self, request):
        s = LandlordRegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        email = data["email"].strip().lower()

        if User.objects.filter(email=email).exists():
            return Response(
                {"detail": "An account with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_user(
            email=email,
            full_name=data.get("fullName", ""),
            phone=data.get("phone", ""),
            role=UserRole.LANDLORD,
            is_active=False,
            verification_status=VerificationStatus.PENDING,
        )

        profile, _ = LandlordProfile.objects.get_or_create(user=user)
        profile.property_address = data.get("propertyAddress", "")
        profile.property_type = data.get("propertyType", "")
        profile.number_of_properties = data.get("numberOfProperties", "")
        profile.bedrooms = data.get("bedrooms", "")
        profile.current_status = data.get("currentStatus", "")
        profile.expected_rent = data.get("expectedRent", "")
        profile.services_required = data.get("servicesRequired", "")
        profile.additional_info = data.get("additionalInfo", "")
        profile.save()

        return Response(
            {
                "message": "Registration submitted. Admin verification pending. You will receive login details by email after approval."
            },
            status=status.HTTP_201_CREATED,
        )


# -----------------------------
# PUBLIC REGISTER: STUDENT
# -----------------------------
@method_decorator(csrf_protect, name="dispatch")
class PublicRegisterStudentView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [PublicRegistrationRateThrottle]

    @transaction.atomic
    def post(self, request):
        s = StudentRegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        email = data["email"].strip().lower()

        if User.objects.filter(email=email).exists():
            return Response(
                {"detail": "An account with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_user(
            email=email,
            full_name=data.get("fullName", ""),
            phone=data.get("phone", ""),
            role=UserRole.STUDENT,
            is_active=False,
            verification_status=VerificationStatus.PENDING,
        )

        profile, _ = StudentProfile.objects.get_or_create(user=user)
        profile.nationality = data.get("nationality", "")
        profile.university = data.get("university", "")
        profile.course = data.get("course", "")
        profile.arrival_date = data.get("arrivalDate")
        profile.accommodation_type = data.get("accommodationType", "")
        profile.budget = data.get("budget", "")
        profile.services_needed = data.get("servicesNeeded", "")
        profile.additional_info = data.get("additionalInfo", "")
        profile.save()

        return Response(
            {
                "message": "Registration submitted. Admin verification pending. You will receive login details by email after approval."
            },
            status=status.HTTP_201_CREATED,
        )


# -----------------------------
# PUBLIC QUESTIONS
# -----------------------------
class PublicQuestionsView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        role = (request.query_params.get("role") or "").strip().upper()
        if role not in [UserRole.LANDLORD, UserRole.STUDENT]:
            return Response({"detail": "role must be LANDLORD or STUDENT"}, status=status.HTTP_400_BAD_REQUEST)

        qs = Question.objects.filter(
            target_role=role,
            is_active=True,
        ).order_by("sort_order", "created_at")

        return Response(QuestionSerializer(qs, many=True).data, status=status.HTTP_200_OK)


# -----------------------------
# SAVE ANSWERS (AUTH REQUIRED)
# -----------------------------
class AnswerUpsertView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        s = AnswerUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        answers = s.validated_data["answers"]
        user = request.user

        saved = 0
        for item in answers:
            qid = item.get("question_id")
            text = item.get("answer_text", "")

            if not qid:
                continue

            q = Question.objects.filter(id=qid, is_active=True).first()
            if not q:
                continue
            if q.target_role != user.role:
                continue

            Answer.objects.update_or_create(
                user=user,
                question=q,
                defaults={"answer_text": text},
            )
            saved += 1

        return Response({"message": "Answers saved", "saved": saved}, status=status.HTTP_200_OK)


# -----------------------------
# LOGIN
# -----------------------------
@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        ip = get_client_ip(request)
        ua = get_user_agent(request)

        serializer = LoginSerializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            email_attempted = (request.data.get("email") or "").strip().lower()
            LoginAudit.objects.create(
                user=None,
                email_attempted=email_attempted,
                success=False,
                failure_reason="Invalid credentials",
                ip_address=ip,
                user_agent=ua,
            )
            return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        user = serializer.validated_data["user"]

        if (not user.is_active) or (user.verification_status != VerificationStatus.APPROVED):
            LoginAudit.objects.create(
                user=user,
                email_attempted=user.email,
                success=False,
                failure_reason="Not approved",
                ip_address=ip,
                user_agent=ua,
            )
            return Response(
                {"detail": "Your account is pending admin approval."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # create django session
        user.backend = "django.contrib.auth.backends.ModelBackend"
        dj_login(request, user)

        LoginAudit.objects.create(
            user=user,
            email_attempted=user.email,
            success=True,
            ip_address=ip,
            user_agent=ua,
        )

        user.last_login_ip = ip
        user.last_login_at = timezone.now()
        user.save(update_fields=["last_login_ip", "last_login_at"])

        return Response(
            {"message": "Login success", "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


# -----------------------------
# LOGOUT
# -----------------------------
@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        dj_logout(request)
        response = Response({"message": "Logout success"}, status=status.HTTP_200_OK)
        response.delete_cookie("sessionid")
        return response


# -----------------------------
# OTP: REQUEST
# -----------------------------
@method_decorator(csrf_protect, name="dispatch")
class ForgotPasswordOTPRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetRequestRateThrottle]

    def post(self, request):
        s = ForgotPasswordOTPRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"].strip().lower()

        user = User.objects.filter(email=email).first()
        if not user:
            return Response({"message": "If the email exists, OTP was sent."}, status=status.HTTP_200_OK)

        if not user.is_active:
            return Response({"detail": "Account not approved yet"}, status=status.HTTP_400_BAD_REQUEST)

        PasswordResetOTP.objects.filter(
            user=user,
            used_at__isnull=True
        ).update(used_at=timezone.now())

        otp = PasswordResetOTP.generate_otp()
        PasswordResetOTP.create_for_user(user=user, otp=otp)

        email_send_otp(
            to_email=user.email,
            name=user.full_name or user.email,
            otp=otp,
        )
        return Response({"message": "OTP sent to email"}, status=status.HTTP_200_OK)


# -----------------------------
# OTP: VERIFY + SET NEW PASSWORD
# -----------------------------
@method_decorator(csrf_protect, name="dispatch")
class ForgotPasswordOTPVerifyView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetVerifyRateThrottle]

    @transaction.atomic
    def post(self, request):
        s = ForgotPasswordOTPVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)

        email = s.validated_data["email"].strip().lower()
        otp = s.validated_data["otp"].strip()
        new_password = s.validated_data["new_password"]

        user = User.objects.filter(email=email).first()
        if not user:
            return Response({"detail": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        t = PasswordResetOTP.objects.filter(
            user=user,
            used_at__isnull=True,
        ).order_by("-created_at").first()

        if not t:
            return Response({"detail": "Invalid or used OTP"}, status=status.HTTP_400_BAD_REQUEST)

        if timezone.now() - t.created_at > timezone.timedelta(minutes=10):
            return Response({"detail": "OTP expired"}, status=status.HTTP_400_BAD_REQUEST)

        if t.attempts >= 5:
            return Response(
                {"detail": "Too many invalid OTP attempts. Request a new OTP."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not t.verify(otp):
            t.attempts += 1
            t.save(update_fields=["attempts"])
            return Response({"detail": "Invalid or used OTP"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=["password"])

        t.used_at = timezone.now()
        t.save(update_fields=["used_at"])

        return Response({"message": "Password reset successful"}, status=status.HTTP_200_OK)
