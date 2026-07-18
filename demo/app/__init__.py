from dotenv import load_dotenv
load_dotenv()
from flask import Flask, redirect, url_for
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone
from app.exts import db, login_manager, mail, csrf, migrate
from app.socketio_ext import socketio
from app.models import User, Ticket, Category, Priority, Status, Comment, Notification
from app.utils.seed import seed_it_service_desk
import unittest
import coverage
import os

def create_app(config_object=None):
	app = Flask(__name__)
	# Configuration
	if config_object is not None:
		app.config.from_object(config_object)
	elif os.getenv("FLASK_ENV", "development").lower() == "production":
		app.config.from_object("config.ProductionConfig")
	else:
		app.config.from_object("config.DevelopmentConfig")

	db.init_app(app)
	login_manager.init_app(app)

	migrate.init_app(app, db)
	mail.init_app(app)
	csrf.init_app(app)
	socketio.init_app(app)

	# Import once so the shared Socket.IO handlers are registered.
	from app import socket_events  # noqa: F401

	from app.auth.views import auth_blueprint
	from app.admin.views import admin_blueprint
	from app.agent.views import agent_blueprint
	from app.customer.views import customer_blueprint
	

	app.register_blueprint(auth_blueprint)
	app.register_blueprint(admin_blueprint, url_prefix='/admin')
	app.register_blueprint(agent_blueprint, url_prefix='/agent')
	app.register_blueprint(customer_blueprint, url_prefix='/customer')

	@app.route('/')
	def home():
		return redirect(url_for('auth.login'))

	@app.cli.command('test')
	def test():
		"""Runs the unit tests."""
		tests = unittest.TestLoader().discover('.')
		unittest.TextTestRunner(verbosity=2).run(tests)

	@app.cli.command('cov')
	def cov():
		"""Runs the unit tests with coverage."""
		cov = coverage.coverage(
			branch=True,
			include='app/*'
		)
		cov.start()
		tests = unittest.TestLoader().discover('.')
		unittest.TextTestRunner(verbosity=2).run(tests)
		cov.stop()
		cov.save()
		print('Coverage Summary:')
		cov.report()
		basedir = os.path.abspath(os.path.dirname(__file__))
		covdir = os.path.join(basedir, 'coverage')
		cov.html_report(directory=covdir)
		cov.erase()

	@app.cli.command("seed_it")
	def seed_it_command():
		"""Seed IT Service Desk data."""
		seed_it_service_desk(reset=True)

	@app.cli.command("seed_production")
	def seed_production_command():
		"""Add missing IT reference data without deleting production data."""
		seed_it_service_desk(reset=False)

	@app.cli.command("create_production_staff")
	def create_production_staff_command():
		"""Create/update initial admin and optional agent from environment variables."""
		def upsert_staff(prefix, role):
			email = (os.getenv(f"{prefix}_EMAIL") or "").strip().lower()
			password = os.getenv(f"{prefix}_PASSWORD") or ""
			name = (os.getenv(f"{prefix}_NAME") or role).strip()

			if not email or not password:
				print(f"Skipping {role}: {prefix}_EMAIL or {prefix}_PASSWORD is missing.")
				return

			user = User.query.filter_by(email=email).first()
			if user is None:
				user = User(
					name=name,
					email=email,
					password=generate_password_hash(password),
					role=role,
					email_verified=True,
					email_verified_at=datetime.now(timezone.utc),
				)
				db.session.add(user)
				print(f"Created {role}: {email}")
			else:
				user.name = name
				user.role = role
				user.password = generate_password_hash(password)
				user.email_verified = True
				user.email_verified_at = datetime.now(timezone.utc)
				print(f"Updated {role}: {email}")

		upsert_staff("ADMIN", "Administrator")
		upsert_staff("AGENT", "Agent")
		db.session.commit()

	@app.shell_context_processor
	def make_shell_context():
		return {
			'db': db,
			'User': User,
			'Ticket': Ticket,
			'Category': Category,
			'Priority': Priority,
			'Status': Status,
			'Comment': Comment,
			'Notification': Notification
		}
	
	return app