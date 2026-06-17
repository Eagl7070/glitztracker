import stripe
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app)
from flask_login import login_required, current_user
from models import db, User

billing_bp = Blueprint("billing", __name__)


def _plan_from_price(price_id):
    if price_id == current_app.config.get("STRIPE_PRO_PRICE_ID"):   return "pro"
    if price_id == current_app.config.get("STRIPE_ELITE_PRICE_ID"): return "elite"
    return "free"


@billing_bp.route("/upgrade")
@login_required
def upgrade():
    return render_template("dashboard/upgrade.html",
        stripe_pk       = current_app.config["STRIPE_PUBLISHABLE_KEY"],
        pro_price_id    = current_app.config["STRIPE_PRO_PRICE_ID"],
        elite_price_id  = current_app.config["STRIPE_ELITE_PRICE_ID"],
    )


@billing_bp.route("/checkout/<plan>")
@login_required
def checkout(plan):
    if plan not in ("pro","elite"):
        return redirect(url_for("billing.upgrade"))
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
    price_id = current_app.config[f"STRIPE_{'PRO' if plan=='pro' else 'ELITE'}_PRICE_ID"]
    if not price_id:
        flash("Stripe not configured yet — contact support.", "error")
        return redirect(url_for("billing.upgrade"))
    try:
        if not current_user.stripe_customer_id:
            c = stripe.Customer.create(email=current_user.email, name=current_user.name)
            current_user.stripe_customer_id = c.id
            db.session.commit()
        base = current_app.config["APP_URL"]
        sess = stripe.checkout.Session.create(
            customer            = current_user.stripe_customer_id,
            payment_method_types= ["card"],
            line_items          = [{"price": price_id, "quantity": 1}],
            mode                = "subscription",
            success_url         = base + url_for("billing.success") + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url          = base + url_for("billing.upgrade"),
        )
        return redirect(sess.url)
    except Exception as e:
        flash(f"Checkout error: {e}", "error")
        return redirect(url_for("billing.upgrade"))


@billing_bp.route("/success")
@login_required
def success():
    flash("🎉 Subscription activated! Welcome to the next level.", "success")
    return redirect(url_for("dashboard.home"))


@billing_bp.route("/portal")
@login_required
def portal():
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
    if not current_user.stripe_customer_id:
        flash("No billing account found.", "error")
        return redirect(url_for("billing.upgrade"))
    try:
        sess = stripe.billing_portal.Session.create(
            customer   = current_user.stripe_customer_id,
            return_url = current_app.config["APP_URL"] + url_for("dashboard.home"),
        )
        return redirect(sess.url)
    except Exception as e:
        flash(f"Portal error: {e}", "error")
        return redirect(url_for("dashboard.home"))


@billing_bp.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data(as_text=True)
    sig     = request.headers.get("Stripe-Signature","")
    secret  = current_app.config.get("STRIPE_WEBHOOK_SECRET","")
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except stripe.error.SignatureVerificationError:
        return "Bad signature", 400
    except Exception as e:
        return f"Error: {e}", 400

    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
    obj = event["data"]["object"]

    if event["type"] == "checkout.session.completed":
        user = User.query.filter_by(stripe_customer_id=obj.get("customer")).first()
        if user and obj.get("subscription"):
            sub = stripe.Subscription.retrieve(obj["subscription"])
            user.stripe_subscription_id = sub["id"]
            user.plan = _plan_from_price(sub["items"]["data"][0]["price"]["id"])
            user.subscription_status = sub["status"]
            db.session.commit()

    elif event["type"] in ("customer.subscription.updated","customer.subscription.deleted"):
        user = User.query.filter_by(stripe_customer_id=obj.get("customer")).first()
        if user:
            if event["type"] == "customer.subscription.deleted":
                user.plan = "free"; user.subscription_status = "canceled"
                user.stripe_subscription_id = None
            else:
                user.plan = _plan_from_price(obj["items"]["data"][0]["price"]["id"])
                user.subscription_status = obj["status"]
            db.session.commit()

    elif event["type"] == "invoice.payment_failed":
        user = User.query.filter_by(stripe_customer_id=obj.get("customer")).first()
        if user:
            user.subscription_status = "past_due"; db.session.commit()

    return "", 200
