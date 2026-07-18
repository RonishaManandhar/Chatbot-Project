from flask_wtf import FlaskForm
from wtforms import StringField, EmailField, PasswordField, BooleanField
from wtforms.validators import DataRequired, ValidationError, Email, Length
from app.models import User
import re

class SignupForm(FlaskForm):
    name = StringField('Name',
        validators=[DataRequired(), Length(min=4, max=32)])

    email = EmailField('Email',
        validators=[DataRequired(), Email(), Length(min=6, max=64)])

    password = PasswordField('Password',
        validators=[DataRequired(), Length(min=8, max=64)])

    agree = BooleanField('I agree to the Terms and Conditions',
        validators=[DataRequired()])

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('This e-mail address is already taken')

    def validate_password(self, password):
        pwd = password.data or ""

        if len(pwd) < 8:
            raise ValidationError("Password is too weak. Use at least 8 characters.")

        if not re.search(r"[A-Z]", pwd):
            raise ValidationError("Password is too weak. Add at least one uppercase letter.")

        if not re.search(r"[a-z]", pwd):
            raise ValidationError("Password is too weak. Add at least one lowercase letter.")

        if not re.search(r"\d", pwd):
            raise ValidationError("Password is too weak. Add at least one number.")

        if not re.search(r"[^\w\s]", pwd):
            raise ValidationError("Password is too weak. Add at least one special character, for example ! @ # $.")

class LoginForm(FlaskForm):
	email = EmailField('Email',
		validators=[DataRequired(), Email()])
	password = PasswordField('Password',
		validators=[DataRequired()])
	remember = BooleanField('Remember me')

class ForgotPasswordForm(FlaskForm):
	email = EmailField('Email',
		validators=[DataRequired(), Email()])

	def validate_email(self, email):
		user = User.query.filter_by(email=email.data).first()
		if user is None:
			raise ValidationError('This e-mail address doesn\'t exist')

class ResetPasswordForm(FlaskForm):
	password = PasswordField('New Password',
		validators=[DataRequired(), Length(min=6, max=32)])