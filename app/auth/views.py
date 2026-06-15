from flask import Blueprint, render_template as _render, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user

from app.auth.forms import LoginForm, SignupForm, ForgotPasswordForm, ResetPasswordForm
from app.utils.redirect_url_endpoint import url_destination
from app.utils.reset_password import send_reset_link
from app.models import User, Notification, SystemEvent
from app.exts import db
from flask import request
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

auth_blueprint = Blueprint('auth', __name__)

def log_system_event(event_type, message, severity="Info", user_id=None, ticket_id=None):
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

    except Exception as e:
        db.session.rollback()
        print("SYSTEM EVENT LOG ERROR:", e)



# Pass variable to all templates
def render_template(*args, **kwargs):
	year = datetime.date.today().year
	return _render(*args, **kwargs, year=year)
@auth_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    requested_next = request.args.get("next")
    next_url = None

    if requested_next and requested_next.startswith("/"):
        next_url = requested_next

    if current_user.is_authenticated:
        if next_url:
            return redirect(next_url)

        if current_user.role == 'Administrator':
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'Agent':
            return redirect(url_for('agent.dashboard'))

        return redirect(url_for('customer.dashboard'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        # Existing user but account temporarily locked
        if user and user.locked_until:
            now = datetime.datetime.utcnow()

            if user.locked_until > now:
                flash("Too many failed attempts. Please try again later.", "danger")
                return render_template('auth/login.html', form=form)

            # Lock expired, reset counters
            user.locked_until = None
            user.failed_login_attempts = 0
            db.session.commit()

        # Correct credentials
        if user and check_password_hash(user.password, form.password.data):
            user.failed_login_attempts = 0
            user.locked_until = None
            db.session.commit()

            login_user(user, remember=form.remember.data)

            if next_url:
                return redirect(next_url)

            if user.role == 'Administrator':
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'Agent':
                return redirect(url_for('agent.dashboard'))

            return redirect(url_for('customer.dashboard'))

        # Wrong credentials
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

            if user.failed_login_attempts >= 5:
                user.locked_until = (
                    datetime.datetime.utcnow()
                    + datetime.timedelta(minutes=15)
                )

                db.session.commit()

                log_system_event(
                    event_type="Account Locked",
                    severity="Critical",
                    message=f"Account locked after 5 failed login attempts for {user.email}.",
                    user_id=user.id
                )

                admins = User.query.filter_by(role="Administrator").all()

                for admin in admins:
                    Notification.send_notification(
                        message=f"Security alert: account locked after 5 failed login attempts for {user.email}.",
                        receiver_id=admin.id,
                        sender_id=user.id,
                        ticket_id=None,
                        seen=False
                    )

                flash(
                    "Max attempts reached. Account locked temporarily for 15 minutes.",
                    "danger"
                )

            else:
                db.session.commit()

                remaining = 5 - user.failed_login_attempts

                flash(
                    f"Incorrect email or password. Attempts remaining: {remaining}",
                    "danger"
                )

        else:
            flash("Incorrect email or password.", "danger")

    return render_template('auth/login.html', form=form)

@auth_blueprint.route('/signup', methods=['GET', 'POST'])
def signup():
	if current_user.is_authenticated and current_user.role == 'Administrator':
		return url_destination(fallback=url_for('admin.dashboard'))
	elif current_user.is_authenticated and current_user.role == 'Agent':
		return url_destination(fallback=url_for('agent.dashboard'))
	elif current_user.is_authenticated and current_user.role == 'Customer':
		return url_destination(fallback=url_for('customer.dashboard'))
		
	form = SignupForm()
	if form.validate_on_submit():
		hashed_password = generate_password_hash(form.password.data)
		role = 'Customer'
		image = 'default-profile.png'
		user = User(
			name=form.name.data,
			email=form.email.data,
			password=hashed_password,
			role=role,
			image=image
		)
		db.session.add(user)
		db.session.commit()

		flash('Your account has been created.', 'primary')
		return redirect(url_for('auth.login'))
	return render_template('auth/signup.html', form=form)

@auth_blueprint.route('/logout')
def logout():
	logout_user()
	return redirect(url_for('auth.login'))

@auth_blueprint.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
	if current_user.is_authenticated and current_user.role == 'Administrator':
		return url_destination(fallback=url_for('admin.dashboard'))
	elif current_user.is_authenticated and current_user.role == 'Agent':
		return url_destination(fallback=url_for('agent.dashboard'))
	elif current_user.is_authenticated and current_user.role == 'Customer':
		return url_destination(fallback=url_for('customer.dashboard'))

	form = ForgotPasswordForm()
	if form.validate_on_submit():
		user = User.query.filter_by(email=form.email.data).first()
		send_reset_link(user)
		flash('Check your email for a link to reset your password.', 'primary')
		return redirect(url_for('auth.login'))
	return render_template('auth/forgot_password.html', form=form)

@auth_blueprint.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
	if current_user.is_authenticated and current_user.role == 'Administrator':
		return url_destination(fallback=url_for('admin.dashboard'))
	elif current_user.is_authenticated and current_user.role == 'Agent':
		return url_destination(fallback=url_for('agent.dashboard'))
	elif current_user.is_authenticated and current_user.role == 'Customer':
		return url_destination(fallback=url_for('customer.dashboard'))

	user = User.verify_reset_token(token)
	if user is None:
		flash('Invalid or expired token, please try again!', 'warning')
		return redirect(url_for('auth.forgot_password'))

	form = ResetPasswordForm()
	if form.validate_on_submit():
		hashed_password = generate_password_hash(form.password.data)
		user.password = hashed_password
		db.session.commit()

		flash('Your password has been updated.', 'primary')
		return redirect(url_for('auth.login'))
	return render_template('auth/reset_password.html', form=form)