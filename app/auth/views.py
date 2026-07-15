import datetime
import secrets

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template as _render,
    request,
    session,
    url_for
)
from flask_login import (
    current_user,
    login_user,
    logout_user
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from app.auth.forms import (
    ForgotPasswordForm,
    LoginForm,
    ResetPasswordForm,
    SignupForm
)
from app.exts import db
from app.models import (
    EmailPreference,
    EmailVerificationCode,
    Notification,
    SystemEvent,
    User
)
from app.services.email_service import (
    send_login_otp_email,
    send_password_changed_email,
    send_password_reset_email,
    send_verification_email
)
from app.utils.redirect_url_endpoint import url_destination


auth_blueprint = Blueprint(
    "auth",
    __name__
)


# ============================================================
# TEMPLATE HELPER
# ============================================================

def render_template(*args, **kwargs):
    year = datetime.date.today().year
    return _render(
        *args,
        **kwargs,
        year=year
    )


# ============================================================
# SYSTEM EVENT HELPER
# ============================================================

def log_system_event(
    event_type,
    message,
    severity="Info",
    user_id=None,
    ticket_id=None
):
    try:
        event = SystemEvent(
            event_type=event_type,
            severity=severity,
            message=message,
            user_id=user_id,
            related_ticket_id=ticket_id
        )

        db.session.add(event)
        db.session.commit()

        return event

    except Exception as error:
        db.session.rollback()

        current_app.logger.exception(
            "SYSTEM EVENT LOG ERROR: %s",
            error
        )

        return None


# ============================================================
# OTP HELPERS
# ============================================================

def generate_six_digit_code():
    """
    Generate a cryptographically secure six-digit OTP.
    """

    return f"{secrets.randbelow(900000) + 100000:06d}"


def invalidate_existing_codes(user_id, purpose):
    """
    Mark any previous unused codes for this user and purpose as used.
    This ensures only the newest OTP remains valid.
    """

    old_codes = (
        EmailVerificationCode.query
        .filter(
            EmailVerificationCode.user_id == user_id,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.used == False
        )
        .all()
    )

    now = datetime.datetime.utcnow()

    for code_record in old_codes:
        code_record.used = True
        code_record.used_at = now


def create_verification_code(
    user,
    purpose,
    expiry_minutes=10
):
    """
    Create and store a hashed one-time code.

    The plain OTP is returned only so it can be emailed.
    The database stores only the password hash.
    """

    invalidate_existing_codes(
        user_id=user.id,
        purpose=purpose
    )

    plain_code = generate_six_digit_code()

    code_record = EmailVerificationCode(
        user_id=user.id,
        code_hash=generate_password_hash(
            plain_code
        ),
        purpose=purpose,
        expires_at=(
            datetime.datetime.utcnow()
            + datetime.timedelta(
                minutes=expiry_minutes
            )
        ),
        used=False,
        attempts=0
    )

    db.session.add(code_record)
    db.session.commit()

    # TEMPORARY DEVELOPMENT OTP
    print("\n")
    print("========================================")
    print("LOGIN OTP CODE")
    print("Email:", user.email)
    print("Purpose:", purpose)
    print("OTP:", plain_code)
    print("========================================")
    print("\n")

    return plain_code


def get_latest_active_code(user_id, purpose):
    return (
        EmailVerificationCode.query
        .filter(
            EmailVerificationCode.user_id == user_id,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.used == False
        )
        .order_by(
            EmailVerificationCode.created_at.desc(),
            EmailVerificationCode.id.desc()
        )
        .first()
    )


def validate_verification_code(
    user,
    submitted_code,
    purpose
):
    """
    Returns:
        (True, "success")
        (False, reason)
    """

    submitted_code = (
        submitted_code or ""
    ).strip()

    if not submitted_code:
        return False, "Please enter the six-digit code."

    code_record = get_latest_active_code(
        user_id=user.id,
        purpose=purpose
    )

    if not code_record:
        return (
            False,
            "No active verification code was found. "
            "Please request a new code."
        )

    now = datetime.datetime.utcnow()

    if now > code_record.expires_at:
        code_record.used = True
        code_record.used_at = now

        db.session.commit()

        return (
            False,
            "This verification code has expired. "
            "Please request a new code."
        )

    if code_record.attempts >= 5:
        code_record.used = True
        code_record.used_at = now

        db.session.commit()

        return (
            False,
            "Too many incorrect attempts. "
            "Please request a new code."
        )

    if not check_password_hash(
        code_record.code_hash,
        submitted_code
    ):
        code_record.attempts += 1

        attempts_remaining = max(
            0,
            5 - code_record.attempts
        )

        if code_record.attempts >= 5:
            code_record.used = True
            code_record.used_at = now

        db.session.commit()

        if attempts_remaining == 0:
            return (
                False,
                "Too many incorrect attempts. "
                "Please request a new code."
            )

        return (
            False,
            f"Incorrect verification code. "
            f"Attempts remaining: {attempts_remaining}."
        )

    code_record.used = True
    code_record.used_at = now

    db.session.commit()

    return True, "success"


# ============================================================
# DESTINATION HELPER
# ============================================================

def redirect_user_to_dashboard(user):
    if user.role == "Administrator":
        return redirect(
            url_for("admin.dashboard")
        )

    if user.role == "Agent":
        return redirect(
            url_for("agent.dashboard")
        )

    return redirect(
        url_for("customer.dashboard")
    )


# ============================================================
# LOGIN
# ============================================================

@auth_blueprint.route(
    "/login",
    methods=["GET", "POST"]
)
def login():
    requested_next = (
        request.args.get("next")
        or session.get("login_next_url")
    )

    next_url = None

    if (
        requested_next
        and requested_next.startswith("/")
        and not requested_next.startswith("//")
    ):
        next_url = requested_next

    if current_user.is_authenticated:
        if next_url:
            session.pop(
                "login_next_url",
                None
            )

            return redirect(next_url)

        return redirect_user_to_dashboard(
            current_user
        )

    form = LoginForm()

    if form.validate_on_submit():
        email = (
            form.email.data or ""
        ).strip().lower()

        user = User.query.filter_by(
            email=email
        ).first()

        # ----------------------------------------------------
        # TEMPORARY ACCOUNT LOCK CHECK
        # ----------------------------------------------------

        if user and user.locked_until:
            now = datetime.datetime.utcnow()

            if user.locked_until > now:
                flash(
                    "Too many failed login attempts. "
                    "Please try again later.",
                    "danger"
                )

                return render_template(
                    "auth/login.html",
                    form=form
                )

            user.locked_until = None
            user.failed_login_attempts = 0

            db.session.commit()

        # ----------------------------------------------------
        # CORRECT CREDENTIALS
        # ----------------------------------------------------

        if (
            user
            and check_password_hash(
                user.password,
                form.password.data
            )
        ):
            user.failed_login_attempts = 0
            user.locked_until = None

            db.session.commit()

            # Account must first complete registration verification.
            if not user.email_verified:
                session[
                    "pending_verification_user_id"
                ] = user.id

                code = create_verification_code(
                    user=user,
                    purpose="register"
                )

                email_sent = send_verification_email(
                    user,
                    code
                )

                if email_sent:
                    flash(
                        "Your email is not verified. "
                        "A new verification code was sent.",
                        "warning"
                    )
                else:
                    flash(
                        "Your email is not verified, but the "
                        "verification email could not be sent. "
                        "Please try resending it.",
                        "danger"
                    )

                return redirect(
                    url_for(
                        "auth.verify_email",
                        user_id=user.id
                    )
                )

            # Save login information until OTP succeeds.
            session["pending_login_user_id"] = user.id
            session["pending_login_remember"] = bool(
                form.remember.data
            )

            if next_url:
                session["login_next_url"] = next_url
            else:
                session.pop(
                    "login_next_url",
                    None
                )

            login_code = create_verification_code(
                user=user,
                purpose="login"
            )

            email_sent = send_login_otp_email(
                user,
                login_code
            )

            if not email_sent:
                flash(
                    "The email could not be sent. "
                    "For local testing, use the OTP shown "
                    "in the terminal.",
                    "warning"
                )

                return redirect(
                    url_for("auth.verify_login_otp")
                )

            log_system_event(
                event_type="Login OTP Sent",
                severity="Info",
                message=(
                    f"A login verification code was sent "
                    f"to {user.email}."
                ),
                user_id=user.id
            )

            flash(
                "A one-time login code has been sent "
                "to your email.",
                "primary"
            )

            return redirect(
                url_for("auth.verify_login_otp")
            )

        # ----------------------------------------------------
        # WRONG CREDENTIALS
        # ----------------------------------------------------

        if user:
            user.failed_login_attempts = (
                user.failed_login_attempts or 0
            ) + 1

            if user.failed_login_attempts >= 5:
                user.locked_until = (
                    datetime.datetime.utcnow()
                    + datetime.timedelta(
                        minutes=15
                    )
                )

                db.session.commit()

                log_system_event(
                    event_type="Account Locked",
                    severity="Critical",
                    message=(
                        "Account locked after five failed "
                        f"login attempts for {user.email}."
                    ),
                    user_id=user.id
                )

                admins = User.query.filter_by(
                    role="Administrator"
                ).all()

                for admin in admins:
                    Notification.send_notification(
                        message=(
                            "Security alert: account locked "
                            "after five failed login attempts "
                            f"for {user.email}."
                        ),
                        receiver_id=admin.id,
                        sender_id=user.id,
                        ticket_id=None,
                        seen=False
                    )

                flash(
                    "Maximum attempts reached. "
                    "Your account is temporarily locked "
                    "for 15 minutes.",
                    "danger"
                )

            else:
                db.session.commit()

                remaining = (
                    5 - user.failed_login_attempts
                )

                flash(
                    "Incorrect email or password. "
                    f"Attempts remaining: {remaining}.",
                    "danger"
                )

        else:
            # Generic message prevents account enumeration.
            flash(
                "Incorrect email or password.",
                "danger"
            )

    return render_template(
        "auth/login.html",
        form=form
    )


# ============================================================
# VERIFY LOGIN OTP
# ============================================================

@auth_blueprint.route(
    "/verify-login-otp",
    methods=["GET", "POST"]
)
def verify_login_otp():
    if current_user.is_authenticated:
        return redirect_user_to_dashboard(
            current_user
        )

    pending_user_id = session.get(
        "pending_login_user_id"
    )

    if not pending_user_id:
        flash(
            "Your login verification session has expired. "
            "Please log in again.",
            "warning"
        )

        return redirect(
            url_for("auth.login")
        )

    user = User.query.get(
        pending_user_id
    )

    if not user:
        session.pop(
            "pending_login_user_id",
            None
        )
        session.pop(
            "pending_login_remember",
            None
        )
        session.pop(
            "login_next_url",
            None
        )

        flash(
            "The account could not be found.",
            "danger"
        )

        return redirect(
            url_for("auth.login")
        )

    if request.method == "POST":
        submitted_code = request.form.get(
            "code"
        )

        valid, message = validate_verification_code(
            user=user,
            submitted_code=submitted_code,
            purpose="login"
        )

        if not valid:
            flash(
                message,
                "danger"
            )

            return render_template(
                "auth/login_otp.html",
                user=user
            )

        remember_login = bool(
            session.get(
                "pending_login_remember",
                False
            )
        )

        login_user(
            user,
            remember=remember_login
        )

        next_url = session.pop(
            "login_next_url",
            None
        )

        session.pop(
            "pending_login_user_id",
            None
        )
        session.pop(
            "pending_login_remember",
            None
        )

        log_system_event(
            event_type="Login Successful",
            severity="Info",
            message=(
                f"Login OTP verified successfully "
                f"for {user.email}."
            ),
            user_id=user.id
        )

        flash(
            "Login verification successful.",
            "success"
        )

        if (
            next_url
            and next_url.startswith("/")
            and not next_url.startswith("//")
        ):
            return redirect(next_url)

        return redirect_user_to_dashboard(
            user
        )

    return render_template(
        "auth/login_otp.html",
        user=user
    )


# ============================================================
# RESEND LOGIN OTP
# ============================================================

@auth_blueprint.route(
    "/resend-login-otp",
    methods=["POST"]
)
def resend_login_otp():
    pending_user_id = session.get(
        "pending_login_user_id"
    )

    if not pending_user_id:
        flash(
            "Your login verification session expired. "
            "Please log in again.",
            "warning"
        )

        return redirect(
            url_for("auth.login")
        )

    user = User.query.get(
        pending_user_id
    )

    if not user:
        flash(
            "The account could not be found.",
            "danger"
        )

        return redirect(
            url_for("auth.login")
        )

    code = create_verification_code(
        user=user,
        purpose="login"
    )

    email_sent = send_login_otp_email(
        user,
        code
    )

    if email_sent:
        flash(
            "A new login code was sent to your email.",
            "success"
        )
    else:
        flash(
            "The login code could not be sent. "
            "Please try again.",
            "danger"
        )

    return redirect(
        url_for("auth.verify_login_otp")
    )


# ============================================================
# SIGNUP
# ============================================================
# ============================================================
# SIGNUP
# ============================================================

@auth_blueprint.route(
    "/signup",
    methods=["GET", "POST"]
)
def signup():
    """
    Register a new customer account.

    Process:
        1. Validate the registration form.
        2. Prevent duplicate email addresses.
        3. Create the user account.
        4. Create the user's default email preferences.
        5. Generate a registration verification OTP.
        6. Send the verification email.
        7. Redirect the customer to the verification page.
    """

    if current_user.is_authenticated:
        return redirect_user_to_dashboard(
            current_user
        )

    form = SignupForm()

    if form.validate_on_submit():
        email = (
            form.email.data or ""
        ).strip().lower()

        name = (
            form.name.data or ""
        ).strip()

        # ----------------------------------------------------
        # CHECK FOR AN EXISTING ACCOUNT
        # ----------------------------------------------------

        existing_user = User.query.filter_by(
            email=email
        ).first()

        if existing_user:
            flash(
                "An account already exists for this email address.",
                "warning"
            )

            return render_template(
                "auth/signup.html",
                form=form
            )

        try:
            # ------------------------------------------------
            # CREATE USER
            # ------------------------------------------------

            user = User(
                name=name,
                email=email,
                password=generate_password_hash(
                    form.password.data
                ),
                role="Customer",
                image="default-profile.png",
                email_verified=False,
                email_verified_at=None
            )

            db.session.add(user)

            # Generate the user ID without committing yet.
            db.session.flush()

            # ------------------------------------------------
            # CREATE DEFAULT EMAIL PREFERENCES
            # ------------------------------------------------

            email_preference = EmailPreference(
                user_id=user.id,
                ticket_updates=True,
                security_emails=True,
                marketing_emails=True,
                satisfaction_emails=True,
                created_at=datetime.datetime.utcnow()
            )

            db.session.add(email_preference)

            # Save the user and preferences together.
            db.session.commit()

        except Exception as error:
            db.session.rollback()

            current_app.logger.exception(
                "ACCOUNT CREATION ERROR: "
                "email=%s error=%s",
                email,
                error
            )

            flash(
                "Your account could not be created. "
                "Please try again.",
                "danger"
            )

            return render_template(
                "auth/signup.html",
                form=form
            )

        # ----------------------------------------------------
        # CREATE REGISTRATION VERIFICATION OTP
        # ----------------------------------------------------

        try:
            verification_code = create_verification_code(
                user=user,
                purpose="register",
                expiry_minutes=10
            )

        except Exception as error:
            current_app.logger.exception(
                "REGISTRATION OTP CREATION ERROR: "
                "user_id=%s email=%s error=%s",
                user.id,
                user.email,
                error
            )

            flash(
                "Your account was created, but the verification "
                "code could not be generated. Please try logging "
                "in again to request a new code.",
                "warning"
            )

            return redirect(
                url_for("auth.login")
            )

        # ----------------------------------------------------
        # SEND REGISTRATION VERIFICATION EMAIL
        # ----------------------------------------------------

        email_sent = send_verification_email(
            user,
            verification_code
        )

        session[
            "pending_verification_user_id"
        ] = user.id

        log_system_event(
            event_type="Account Created",
            severity="Info",
            message=(
                "A new customer account was created "
                f"for {user.email}."
            ),
            user_id=user.id
        )

        if email_sent:
            flash(
                "Your account was created. "
                "Enter the six-digit verification code "
                "sent to your email.",
                "primary"
            )

        else:
            current_app.logger.error(
                "REGISTRATION VERIFICATION EMAIL FAILED: "
                "user_id=%s email=%s",
                user.id,
                user.email
            )

            flash(
                "Your account was created, but the verification "
                "email could not be sent. Select Resend Code "
                "on the verification page.",
                "warning"
            )

        return redirect(
            url_for(
                "auth.verify_email",
                user_id=user.id
            )
        )

    return render_template(
        "auth/signup.html",
        form=form
    )

# ============================================================
# VERIFY REGISTRATION EMAIL
# ============================================================

@auth_blueprint.route(
    "/verify-email/<int:user_id>",
    methods=["GET", "POST"]
)
def verify_email(user_id):
    if current_user.is_authenticated:
        return redirect_user_to_dashboard(
            current_user
        )

    user = User.query.get_or_404(
        user_id
    )

    if user.email_verified:
        flash(
            "This email address is already verified. "
            "You can log in.",
            "success"
        )

        return redirect(
            url_for("auth.login")
        )

    pending_user_id = session.get(
        "pending_verification_user_id"
    )

    if (
        pending_user_id
        and int(pending_user_id) != user.id
    ):
        flash(
            "This verification session does not match "
            "the requested account.",
            "danger"
        )

        return redirect(
            url_for("auth.login")
        )

    if request.method == "POST":
        submitted_code = request.form.get(
            "code"
        )

        valid, message = validate_verification_code(
            user=user,
            submitted_code=submitted_code,
            purpose="register"
        )

        if not valid:
            flash(
                message,
                "danger"
            )

            return render_template(
                "auth/verify_email.html",
                user=user
            )

        user.email_verified = True
        user.email_verified_at = (
            datetime.datetime.utcnow()
        )

        db.session.commit()

        session.pop(
            "pending_verification_user_id",
            None
        )

        log_system_event(
            event_type="Email Verified",
            severity="Info",
            message=(
                f"Email verification completed "
                f"for {user.email}."
            ),
            user_id=user.id
        )

        flash(
            "Your email has been verified successfully. "
            "You can now log in.",
            "success"
        )

        return redirect(
            url_for("auth.login")
        )

    return render_template(
        "auth/verify_email.html",
        user=user
    )


# ============================================================
# RESEND REGISTRATION VERIFICATION CODE
# ============================================================

@auth_blueprint.route(
    "/verify-email/<int:user_id>/resend",
    methods=["POST"]
)
def resend_verification_email(user_id):
    if current_user.is_authenticated:
        return redirect_user_to_dashboard(
            current_user
        )

    user = User.query.get_or_404(
        user_id
    )

    if user.email_verified:
        flash(
            "This email address is already verified.",
            "success"
        )

        return redirect(
            url_for("auth.login")
        )

    code = create_verification_code(
        user=user,
        purpose="register"
    )

    email_sent = send_verification_email(
        user,
        code
    )

    session[
        "pending_verification_user_id"
    ] = user.id

    if email_sent:
        flash(
            "A new verification code was sent.",
            "success"
        )
    else:
        flash(
            "The verification email could not be sent. "
            "Please try again.",
            "danger"
        )

    return redirect(
        url_for(
            "auth.verify_email",
            user_id=user.id
        )
    )


# ============================================================
# LOGOUT
# ============================================================

@auth_blueprint.route("/logout")
def logout():
    logout_user()

    session.pop(
        "pending_login_user_id",
        None
    )
    session.pop(
        "pending_login_remember",
        None
    )
    session.pop(
        "pending_verification_user_id",
        None
    )
    session.pop(
        "login_next_url",
        None
    )

    return redirect(
        url_for("auth.login")
    )


# ============================================================
# FORGOT PASSWORD
# ============================================================

# ============================================================
# FORGOT PASSWORD
# ============================================================

@auth_blueprint.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():
    if current_user.is_authenticated:
        return redirect_user_to_dashboard(
            current_user
        )

    form = ForgotPasswordForm()

    if form.validate_on_submit():
        email = (
            form.email.data or ""
        ).strip().lower()

        user = User.query.filter_by(
            email=email
        ).first()

        if user:
            token = user.get_reset_token()

            email_sent = send_password_reset_email(
                user,
                token
            )

            if email_sent:
                log_system_event(
                    event_type="Password Reset Requested",
                    severity="Info",
                    message=(
                        "A password-reset link was sent "
                        f"to {user.email}."
                    ),
                    user_id=user.id
                )
            else:
                current_app.logger.error(
                    "Password-reset email failed "
                    "for user_id=%s email=%s",
                    user.id,
                    user.email
                )

        flash(
            "If an account exists for that email address, "
            "a password-reset link has been sent.",
            "primary"
        )

        return redirect(
            url_for("auth.login")
        )

    return render_template(
        "auth/forgot_password.html",
        form=form
    )
# ============================================================
# RESET PASSWORD
# ============================================================

@auth_blueprint.route(
    "/reset-password/<token>",
    methods=["GET", "POST"]
)
def reset_password(token):
    if current_user.is_authenticated:
        return redirect_user_to_dashboard(
            current_user
        )

    user = User.verify_reset_token(
        token
    )

    if user is None:
        flash(
            "This password-reset link is invalid or expired. "
            "Please request a new link.",
            "warning"
        )

        return redirect(
            url_for("auth.forgot_password")
        )

    form = ResetPasswordForm()

    if form.validate_on_submit():
        user.password = generate_password_hash(
            form.password.data
        )

        user.failed_login_attempts = 0
        user.locked_until = None

        db.session.commit()

        email_sent = send_password_changed_email(
            user
        )

        if not email_sent:
            current_app.logger.error(
                "Password-changed email failed "
                "for user_id=%s email=%s",
                user.id,
                user.email
            )

        log_system_event(
            event_type="Password Reset Completed",
            severity="Info",
            message=(
                f"Password reset completed "
                f"for {user.email}."
            ),
            user_id=user.id
        )

        flash(
            "Your password has been updated successfully. "
            "You can now log in.",
            "primary"
        )

        return redirect(
            url_for("auth.login")
        )

    return render_template(
        "auth/reset_password.html",
        form=form
    )