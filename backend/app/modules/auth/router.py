"""Authentication endpoints."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import AppError, AuthenticationError
from app.core.logging import get_logger
from app.core.rate_limit import client_ip, enforce_rate_limit
from app.core.time import utcnow
from app.modules.auth import google, service
from app.modules.auth.cookies import (
    clear_refresh_cookie,
    read_refresh_cookie,
    set_refresh_cookie,
)
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    EmailRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SessionResponse,
    SwitchOrgRequest,
    UserRead,
    VerifyEmailRequest,
)
from app.modules.auth.service import ClientInfo, IssuedSession
from app.modules.notifications.email import outbox

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])

GENERIC_EMAIL_REPLY = "If that address has an account, we have sent it an email. Check your inbox."


def _format_moment() -> str:
    """Human-readable timestamp for security notification emails."""
    return utcnow().strftime("%d %B %Y at %H:%M UTC")


def _client(request: Request) -> ClientInfo:
    return ClientInfo(
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(
            request.headers.get("x-forwarded-for"), request.client.host if request.client else None
        ),
    )


def _finish(response: Response, issued: IssuedSession) -> SessionResponse:
    set_refresh_cookie(response, issued.refresh_token, issued.refresh_expires_at)
    return issued.response


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, data: RegisterRequest, session: DbSession) -> RegisterResponse:
    """Create an account and email a verification link.

    The response is identical whether or not the address was already
    registered, so this endpoint cannot be used to discover who has an account.
    """
    await enforce_rate_limit(
        f"register:ip:{_client(request).ip_address}", limit=10, window_seconds=3600
    )

    user, token = await service.register(session, data)
    if token is not None:
        await outbox.enqueue(
            session,
            template_key="verify_email",
            to_email=user.email,
            to_name=user.full_name,
            context={
                "user_name": user.full_name,
                "verify_url": f"{settings.app_url}/verify-email?token={token}",
                "expires_in_hours": settings.email_verify_token_ttl_hours,
            },
        )
    return RegisterResponse(user=UserRead.model_validate(user))


@router.post("/login", response_model=SessionResponse)
async def login(
    request: Request, response: Response, data: LoginRequest, session: DbSession
) -> SessionResponse:
    """Exchange credentials for an access token and a refresh cookie."""
    ip = _client(request).ip_address
    await enforce_rate_limit(f"login:ip:{ip}", limit=20, window_seconds=900)
    await enforce_rate_limit(f"login:email:{data.email.lower()}", limit=10, window_seconds=900)

    user = await service.authenticate(session, email=data.email, password=data.password)
    issued = await service.issue_session(session, user=user, client=_client(request))
    return _finish(response, issued)


@router.post("/refresh", response_model=SessionResponse)
async def refresh(request: Request, response: Response, session: DbSession) -> SessionResponse:
    """Rotate the refresh cookie and mint a new access token."""
    token = read_refresh_cookie(request)
    if not token:
        raise AuthenticationError("No session cookie.", code="missing_refresh_token")

    try:
        issued = await service.rotate_session(session, refresh_token=token, client=_client(request))
    except AuthenticationError:
        clear_refresh_cookie(response)
        raise
    return _finish(response, issued)


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response, session: DbSession) -> MessageResponse:
    """Sign out of this device."""
    token = read_refresh_cookie(request)
    if token:
        await service.revoke_session(session, token)
    clear_refresh_cookie(response)
    return MessageResponse(message="Signed out.")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(response: Response, user: CurrentUser, session: DbSession) -> MessageResponse:
    """Sign out of every device."""
    count = await service.revoke_all_sessions(session, user)
    clear_refresh_cookie(response)
    return MessageResponse(message=f"Signed out of {count} session(s).")


@router.post("/verify-email", response_model=SessionResponse)
async def verify_email(
    request: Request, response: Response, data: VerifyEmailRequest, session: DbSession
) -> SessionResponse:
    """Confirm an email address and sign the user in.

    Signing in here saves the user from typing their password again straight
    after clicking the link in their inbox.
    """
    user = await service.verify_email(session, data.token)
    issued = await service.issue_session(session, user=user, client=_client(request))
    return _finish(response, issued)


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    request: Request, data: EmailRequest, session: DbSession
) -> MessageResponse:
    """Send another verification link."""
    await enforce_rate_limit(
        f"verify:email:{data.email.lower()}",
        limit=3,
        window_seconds=3600,
        message="Too many verification emails requested. Try again in an hour.",
    )

    result = await service.start_email_verification(session, data.email)
    if result is not None:
        user, token = result
        await outbox.enqueue(
            session,
            template_key="verify_email",
            to_email=user.email,
            to_name=user.full_name,
            context={
                "user_name": user.full_name,
                "verify_url": f"{settings.app_url}/verify-email?token={token}",
                "expires_in_hours": settings.email_verify_token_ttl_hours,
            },
        )
    return MessageResponse(message=GENERIC_EMAIL_REPLY)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request: Request, data: EmailRequest, session: DbSession
) -> MessageResponse:
    """Email a password reset link."""
    await enforce_rate_limit(
        f"reset:email:{data.email.lower()}",
        limit=3,
        window_seconds=3600,
        message="Too many reset emails requested. Try again in an hour.",
    )
    await enforce_rate_limit(
        f"reset:ip:{_client(request).ip_address}", limit=20, window_seconds=3600
    )

    result = await service.start_password_reset(session, data.email)
    if result is not None:
        user, token = result
        await outbox.enqueue(
            session,
            template_key="reset_password",
            to_email=user.email,
            to_name=user.full_name,
            context={
                "user_name": user.full_name,
                "reset_url": f"{settings.app_url}/reset-password?token={token}",
                "expires_in_minutes": settings.password_reset_token_ttl_minutes,
            },
        )
    return MessageResponse(message=GENERIC_EMAIL_REPLY)


@router.post("/reset-password", response_model=SessionResponse)
async def reset_password(
    request: Request, response: Response, data: ResetPasswordRequest, session: DbSession
) -> SessionResponse:
    """Set a new password, sign out other devices, and sign this one in."""
    user = await service.reset_password(session, token=data.token, new_password=data.password)
    await outbox.enqueue(
        session,
        template_key="password_changed",
        to_email=user.email,
        to_name=user.full_name,
        context={
            "user_name": user.full_name,
            "changed_at": _format_moment(),
            "support_email": settings.email_reply_to or settings.email_from,
        },
    )
    issued = await service.issue_session(session, user=user, client=_client(request))
    return _finish(response, issued)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    data: ChangePasswordRequest, user: CurrentUser, session: DbSession
) -> MessageResponse:
    """Change the password of the signed-in account."""
    await service.change_password(
        session,
        user=user,
        current_password=data.current_password,
        new_password=data.new_password,
    )
    await outbox.enqueue(
        session,
        template_key="password_changed",
        to_email=user.email,
        to_name=user.full_name,
        context={
            "user_name": user.full_name,
            "changed_at": _format_moment(),
            "support_email": settings.email_reply_to or settings.email_from,
        },
    )
    return MessageResponse(message="Password updated.")


@router.post("/switch-org", response_model=SessionResponse)
async def switch_org(
    request: Request,
    response: Response,
    data: SwitchOrgRequest,
    user: CurrentUser,
    session: DbSession,
) -> SessionResponse:
    """Issue a new token pair scoped to another of the user's organizations."""
    issued = await service.switch_organization(
        session, user=user, org_id=data.org_id, client=_client(request)
    )
    return _finish(response, issued)


@router.get("/me", response_model=SessionResponse)
async def me(user: CurrentUser, session: DbSession, request: Request) -> SessionResponse:
    """The signed-in user with their memberships.

    Returns a fresh access token so a client that has only the refresh cookie
    can bootstrap without a second call.
    """
    issued = await service.issue_session(session, user=user, client=_client(request))
    return issued.response


# --------------------------------------------------------------------------
# Google sign-in
# --------------------------------------------------------------------------
@router.get("/google/start", include_in_schema=True)
async def google_start(request: Request, redirect: str = "/app") -> Any:
    """Begin Google sign-in by redirecting the browser to Google.

    ``redirect`` is where the SPA should land afterwards. Only same-site paths
    are accepted, so this cannot be turned into an open redirect.
    """
    client = google.get_google_client()
    request.session["post_login_redirect"] = _safe_redirect(redirect)
    callback_url = str(request.url_for("google_callback"))
    return await client.authorize_redirect(request, callback_url)


@router.get("/google/callback", name="google_callback", include_in_schema=True)
async def google_callback(request: Request, session: DbSession) -> RedirectResponse:
    """Complete Google sign-in and hand control back to the SPA.

    The refresh cookie is set on the redirect response; the SPA then calls
    ``/auth/refresh`` to obtain its access token.
    """
    target = _safe_redirect(request.session.pop("post_login_redirect", "/app"))
    client = google.get_google_client()

    try:
        profile = await google.exchange_code(client, request)
        user = await google.link_or_create_user(session, profile)
    except AppError as exc:
        logger.info("google_sign_in_failed", code=exc.code)
        failure = RedirectResponse(
            f"{settings.app_url}/auth/google/callback?status=error&code={exc.code}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        return failure

    issued = await service.issue_session(session, user=user, client=_client(request))
    response = RedirectResponse(
        f"{settings.app_url}/auth/google/callback?status=ok&redirect={quote(target, safe='/')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_refresh_cookie(response, issued.refresh_token, issued.refresh_expires_at)
    return response


def _safe_redirect(target: str | None) -> str:
    """Only allow same-site absolute paths.

    ``//evil.example`` and ``https://evil.example`` are both rejected, since a
    protocol-relative path would otherwise leave the site.
    """
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/app"
    return target
