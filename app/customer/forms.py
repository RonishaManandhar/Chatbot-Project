from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed

from wtforms import (
    StringField,
    PasswordField,
    SelectField,
    TextAreaField
)

from wtforms.validators import (
    DataRequired,
    Length,
    EqualTo,
    Optional,
    Email
)




from app.models import Category

allowed_exts = ['pdf', 'docx', 'png', 'jpg', 'jpeg', 'gif']

class TicketForm(FlaskForm):
	subject = StringField('Subject',
		validators=[DataRequired(), Length(min=4, max=128)])
	category = SelectField('Category',
		validators=[DataRequired()])
	body = TextAreaField('Message',
		validators=[DataRequired()])
	attachment = FileField('Attachment',
		validators=[FileAllowed(allowed_exts, 'This file extension is not allowed')])

	def __init__(self, *args, **kwargs):
		super(TicketForm, self).__init__(*args, **kwargs)
		self.category.choices = [('', '-- Please select category --')]+[(category.id, category.category) for category in Category.query.all()]

class UpdateTicketForm(FlaskForm):
	category = SelectField('Category',
		validators=[DataRequired()])

	def __init__(self, *args, **kwargs):
		super(UpdateTicketForm, self).__init__(*args, **kwargs)
		self.category.choices = [('', '-- Please select category --')]+[(category.id, category.category)
			for category in Category.query.all()]

class CommentForm(FlaskForm):
	comment = TextAreaField('Comment',
		validators=[DataRequired()])

class ChangeProfileForm(FlaskForm):
    name = StringField(
        "Full Name",
        validators=[
            DataRequired(),
            Length(min=2, max=255)
        ]
    )

    profile = FileField(
        "Profile Picture",
        validators=[
            Optional(),
            FileAllowed(
                ["png", "jpg", "jpeg"],
                "Only PNG, JPG, and JPEG images are allowed."
            )
        ]
    )

class ChangePasswordForm(
    FlaskForm
):
    current_password = PasswordField(
        "Current Password",
        validators=[
            DataRequired()
        ]
    )

    password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(
                min=6,
                max=32
            )
        ]
    )

    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo(
                "password"
            )
        ]
    )

class ChangeEmailForm(
    FlaskForm
):
    email = StringField(
        "Email",
        validators=[
            DataRequired(),
            Email()
        ]
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired()
        ]
    )