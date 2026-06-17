import random, string
from datetime import datetime, timezone, timedelta
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, session, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from __init__ import bcrypt
from notifier import send_verification_sms

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET","POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))
    if request.method == "POST":
        email    = request.form.get("email","").strip().lower()
        name     = request.form.get("name","").strip()
        password = request.form.get("password","")
        confirm  = request.form.get("confirm","")
        if not email or not password:
            flash("Email and password are required.", "error"); return render_template("auth/register.html")
        if password != confirm:
            flash("Passwords don't match.", "error"); return render_template("auth/register.html")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error"); return render_template("auth/register.html")
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error"); return render_template("auth/register.html")
        hashed = bcrypt.generate_password_hash(password).decode("utf-8")
        user = User(email=email, name=name, password_hash=hashed, plan="free")
        db.session.add(user); db.session.commit()
        login_user(user)
        flash(f"Welcome to GlitzTracker, {name or email}! Your free account is ready.", "success")
        return redirect(url_for("dashboard.home"))
    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))
    if request.method == "POST":
        email    = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        remember = bool(request.form.get("remember"))
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            return redirect(request.args.get("next") or url_for("dashboard.home"))
        flash("Invalid email or password.", "error")
    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("public.index"))


@auth_bp.route("/account", methods=["GET","POST"])
@login_required
def account():
    if request.method == "POST":
        action = request.form.get("action","save")

        if action == "save_profile":
            current_user.name         = request.form.get("name","").strip()
            current_user.alert_email  = request.form.get("alert_email","").strip()
            current_user.notify_email = "notify_email" in request.form
            current_user.notify_telegram = "notify_telegram" in request.form
            current_user.notify_sms   = "notify_sms" in request.form
            current_user.telegram_chat_id = request.form.get("telegram_chat_id","").strip()
            new_pw = request.form.get("new_password","").strip()
            if new_pw:
                if len(new_pw) < 8:
                    flash("Password must be at least 8 characters.", "error")
                    return render_template("auth/account.html")
                current_user.password_hash = bcrypt.generate_password_hash(new_pw).decode("utf-8")
                flash("Password updated.", "success")
            db.session.commit()
            flash("Account saved.", "success")

        elif action == "send_phone_code":
            phone = request.form.get("phone_number","").strip()
            if not phone.startswith("+"):
                flash("Phone must be in E.164 format (e.g. +19725551234).", "error")
            else:
                code = "".join(random.choices(string.digits, k=6))
                session["phone_verify_code"]   = code
                session["phone_verify_number"] = phone
                session["phone_verify_expiry"] = (
                    datetime.now(timezone.utc) + timedelta(minutes=10)
                ).isoformat()
                if send_verification_sms(phone, code):
                    flash(f"Verification code sent to {phone}.", "success")
                else:
                    flash("SMS send failed — check Twilio config.", "error")

        elif action == "verify_phone_code":
            entered  = request.form.get("verify_code","").strip()
            stored   = session.get("phone_verify_code","")
            number   = session.get("phone_verify_number","")
            expiry_s = session.get("phone_verify_expiry","")
            expired  = True
            if expiry_s:
                try:
                    expired = datetime.now(timezone.utc) > datetime.fromisoformat(expiry_s)
                except: pass
            if expired:
                flash("Code expired. Please request a new one.", "error")
            elif entered == stored:
                current_user.phone_number  = number
                current_user.phone_verified = True
                db.session.commit()
                session.pop("phone_verify_code", None)
                flash("Phone number verified! SMS alerts are now active.", "success")
            else:
                flash("Incorrect code. Please try again.", "error")

    return render_template("auth/account.html")
