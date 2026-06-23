import json
from datetime import datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app)
from flask_login import login_required, current_user
from models import db, CashRoute, AwardRoute, SWULog, PriceHistory, CABIN_LABELS, SWU_STATUSES

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def home():
    cash_routes  = CashRoute.query.filter_by(user_id=current_user.id).order_by(CashRoute.created_at).all()
    award_routes = AwardRoute.query.filter_by(user_id=current_user.id).order_by(AwardRoute.created_at).all()
    swu_logs     = SWULog.query.filter_by(user_id=current_user.id).order_by(SWULog.flight_date).all()
    history      = PriceHistory.query.filter_by(user_id=current_user.id)\
                     .order_by(PriceHistory.checked_at.asc()).limit(500).all()
    return render_template("dashboard/home.html",
        cash_routes=cash_routes, award_routes=award_routes,
        swu_logs=swu_logs, history=history,
        cabin_labels=CABIN_LABELS, swu_statuses=SWU_STATUSES,
    )


# ── SWU ───────────────────────────────────────────────────────────────────────
@dashboard_bp.route("/swu/add", methods=["POST"])
@login_required
def swu_add():
    if not current_user.can_swu_track:
        flash("SWU tracking requires the Elite plan.", "error")
        return redirect(url_for("billing.upgrade"))
    f = request.form
    swu = SWULog(
        user_id             = current_user.id,
        airline             = f.get("airline","").upper().strip()[:5],
        flight_number       = f.get("flight_number","").strip()[:10],
        origin              = f.get("origin","").upper().strip()[:5],
        destination         = f.get("destination","").upper().strip()[:5],
        flight_date         = f.get("flight_date","").strip(),
        cabin_requested     = f.get("cabin_requested","business"),
        notes               = f.get("notes","").strip(),
        monitor_award_space = "monitor" in f,
        swu_status          = "pending",
    )
    db.session.add(swu); db.session.commit()
    flash(f"SWU log added for {swu.flight_label}.", "success")
    return redirect(url_for("dashboard.home"))


@dashboard_bp.route("/swu/<int:swu_id>/update", methods=["POST"])
@login_required
def swu_update(swu_id):
    swu = SWULog.query.filter_by(id=swu_id, user_id=current_user.id).first_or_404()
    new_status = request.form.get("status", swu.swu_status)
    swu.swu_status = new_status
    if new_status == "requested" and not swu.requested_at:
        swu.requested_at = datetime.now(timezone.utc)
    if new_status == "cleared" and not swu.cleared_at:
        swu.cleared_at = datetime.now(timezone.utc)
    swu.notes = request.form.get("notes", swu.notes or "")
    db.session.commit()
    flash(f"Updated to: {new_status}.", "success")
    return redirect(url_for("dashboard.home"))


@dashboard_bp.route("/swu/<int:swu_id>/delete", methods=["POST"])
@login_required
def swu_delete(swu_id):
    swu = SWULog.query.filter_by(id=swu_id, user_id=current_user.id).first_or_404()
    db.session.delete(swu); db.session.commit()
    flash("SWU log removed.", "success")
    return redirect(url_for("dashboard.home"))


@dashboard_bp.route("/fifth-freedom")
@login_required
def fifth_freedom():
    return render_template("dashboard/fifth_freedom.html")


@dashboard_bp.route("/calendar")
@login_required
def calendar():
    # Redirect old calendar to cash calendar
    return render_template("dashboard/calendar_cash.html")


@dashboard_bp.route("/calendar/cash")
@login_required
def calendar_cash_page():
    return render_template("dashboard/calendar_cash.html")


@dashboard_bp.route("/calendar/award")
@login_required
def calendar_award_page():
    return render_template("dashboard/calendar_award.html")


@dashboard_bp.route("/calendar/multi")
@login_required
def calendar_multi_page():
    return render_template("dashboard/calendar_multi.html")


@dashboard_bp.route("/explore")
@login_required
def explore():
    return render_template("dashboard/explore.html")
