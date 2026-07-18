# AI-Powered IT Service Desk with Intelligent Triage System

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Flask](https://img.shields.io/badge/Flask-3.x-black)
![MySQL](https://img.shields.io/badge/MySQL-Database-orange)
![Socket.IO](https://img.shields.io/badge/RealTime-SocketIO-green)
![Status](https://img.shields.io/badge/Status-Completed-success)

---

# Table of Contents

- Project Overview
- Objectives
- Key Features
- System Modules
- Technologies Used
- System Architecture
- Database Design
- Application Workflow
- Folder Structure
- Installation Guide
- Environment Configuration
- Database Migration
- Running the Project
- Testing
- Deployment
- Security Features
- Future Enhancements
- Contributors
- License

---

# Project Overview

The AI-Powered IT Service Desk with Intelligent Triage System is a web-based support management platform developed to improve IT service operations through artificial intelligence, automated ticket triage, and real-time communication.

The system aims to reduce manual effort involved in traditional service desk processes by providing:

- Automated issue classification
- Intelligent ticket prioritisation
- Real-time customer support
- Centralised ticket management
- AI-assisted troubleshooting
- Customer satisfaction monitoring

The project follows IT Service Management (ITSM) principles and incorporates AI technologies to improve efficiency and user experience.

---

# Objectives

The primary objectives of this project are:

### Business Objectives

- Improve efficiency of IT support operations.
- Reduce response and resolution times.
- Enhance customer satisfaction.
- Centralise support management activities.
- Reduce manual ticket processing.

### Technical Objectives

- Implement intelligent issue triage.
- Provide real-time communication capabilities.
- Develop scalable system architecture.
- Ensure secure user authentication.
- Support future AI enhancements.

---

# Key Features

# Customer Module

✔ User Registration

✔ OTP Email Verification

✔ Secure Authentication

✔ Profile Management

✔ AI-Based IT Triage Chatbot

✔ Intelligent Ticket Categorisation

✔ Automatic Priority Assignment

✔ Support Ticket Creation

✔ Ticket Tracking

✔ Real-Time Chat

✔ File Upload Support

✔ Knowledge Base Access

✔ FAQ System

✔ Customer Satisfaction Feedback

✔ Ticket Reopening

✔ Notification System

---

# Support Agent Module

✔ Agent Dashboard

✔ View Assigned Tickets

✔ Ticket Status Updates

✔ Priority Management

✔ Ticket Assignment

✔ Ticket Reassignment

✔ Real-Time Customer Communication

✔ Internal Ticket Notes

✔ Ticket Reporting

✔ Knowledge Base Management

✔ FAQ Management

---

# Administrator Module

✔ Complete System Dashboard

✔ User Management

✔ Agent Management

✔ Customer Management

✔ Ticket Monitoring

✔ Analytics Dashboard

✔ Category Management

✔ Priority Management

✔ Status Management

✔ System Maintenance Configuration

✔ Email Monitoring

✔ Activity Logging

✔ Customer Satisfaction Analytics

✔ System Reports

---

# Intelligent Triage Workflow

The AI triage system automatically gathers support information before ticket creation.

The workflow includes:

```text
Customer Issue
       ↓
Issue Type Selection
       ↓
Impact Assessment
       ↓
Urgency Determination
       ↓
Device/Application Information
       ↓
Error Message Collection
       ↓
Additional Description
       ↓
AI Analysis
       ↓
Category Determination
       ↓
Priority Determination
       ↓
Support Recommendation
       ↓
Ticket Creation / Escalation
```

This significantly reduces manual support effort and improves ticket accuracy.

---

# Technologies Used

## Backend

- Python 3.x
- Flask
- SQLAlchemy
- Flask-Migrate
- Flask-Login
- Flask-WTF
- Flask-Mail
- Flask-SocketIO

## Frontend

- HTML5
- CSS3
- Bootstrap 5
- JavaScript
- Jinja2 Templates

## Database

- MySQL

## Artificial Intelligence

- OpenAI API Integration

## Deployment

- Railway

---

# System Architecture

The project follows a Three-Tier Architecture.

## Presentation Layer

Responsible for user interaction.

Components:

- HTML
- CSS
- Bootstrap
- JavaScript

---

## Application Layer

Responsible for business logic.

Components:

- Flask Blueprints
- Authentication Module
- Ticket Module
- AI Service Module
- Notification Module
- Email Service Module
- Socket.IO Module

---

## Data Layer

Responsible for persistent storage.

Components:

- MySQL Database
- SQLAlchemy ORM
- Alembic Migrations

---

# System Modules

## Authentication Module

Responsible for:

- Registration
- Login
- Password Reset
- Email Verification
- Role Management

---

## Customer Support Module

Responsible for:

- AI Chat
- Ticket Management
- Customer Communication
- Ticket Feedback

---

## Administrative Module

Responsible for:

- System Configuration
- Reporting
- Monitoring
- Maintenance

---

# Database Entities

Main entities include:

- User
- Ticket
- Category
- Priority
- Status
- Comment
- ChatMessage
- Notification
- FAQ
- KnowledgeArticle
- CustomerSatisfaction
- AgentReport
- MaintenanceSetting
- EmailLog

---

# Folder Structure

```text
project/
│
├── app/
│   ├── admin/
│   ├── agent/
│   ├── auth/
│   ├── customer/
│   ├── services/
│   ├── static/
│   ├── templates/
│   ├── utils/
│   ├── models.py
│   ├── exts.py
│   └── socket_events.py
│
├── migrations/
├── tests/
├── instance/
├── requirements.txt
├── config.py
├── run.py
└── README.md
```

---

# Installation Guide

## Clone Repository

```bash
git clone https://github.com/username/project-name.git
cd project-name
```

---

## Create Virtual Environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Linux / Mac

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Environment Configuration

Create a `.env` file.

```env
SECRET_KEY=your_secret_key

DB_HOST=localhost
DB_PORT=3306
DB_NAME=it_service_desk
DB_USER=root
DB_PASSWORD=your_password

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=example@gmail.com
MAIL_PASSWORD=your_app_password

OPENAI_API_KEY=your_api_key
```

---

# Database Setup

```bash
flask db init
flask db migrate
flask db upgrade
```

Seed database:

```bash
python seed.py
```

---

# Running the Application

```bash
python run.py
```

or

```bash
flask run
```

Application URL:

```text
http://127.0.0.1:5000
```

---

# Running Tests

```bash
python -m unittest discover tests
```

---

# Deployment

Current deployment platform:

### Railway Cloud Platform

Deployment includes:

- Web Server
- MySQL Database
- Environment Variables
- Production Configuration

---

# Security Features

✔ Password Hashing

✔ Email Verification

✔ Role-Based Access Control

✔ CSRF Protection

✔ Session Management

✔ Secure File Upload Validation

✔ Input Validation

✔ Access Restriction by User Roles

---

# Performance Features

✔ Real-Time Communication using Socket.IO

✔ Modular Architecture

✔ Optimised Database Relationships

✔ Asynchronous Email Services

✔ Responsive User Interface

---

# Future Enhancements

## Functional Improvements

- Machine Learning Ticket Classification
- AI Solution Recommendation Engine
- Sentiment Analysis
- Voice-Based Support Assistant
- Multi-Language Support
- Mobile Application Development
- Microsoft Teams Integration
- Slack Integration

## Non-Functional Improvements

- Docker Containerisation
- Kubernetes Deployment
- Redis Caching
- Load Balancing
- Disaster Recovery System
- Enhanced Monitoring and Logging
- High Availability Architecture

---

# Contributors

| Name | Role |
|------|------|
| Ronisha Manandhar | Developer |
| Angel Pun | Developer |

---

# Academic Information

Course:

NEF3002 Final Year Project

Project Title:

AI-Powered IT Service Desk with Intelligent Triage System

Institution:

(Your University Name)

---

# License

This project is developed solely for educational purposes.

© 2026 All Rights Reserved.