from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

NOTIFY_METHODS  = ["email", "sms", "telegram"]
CABIN_LABELS    = {"economy":"Economy","premium_economy":"Prem Economy","business":"Business","first":"First"}
SWU_STATUSES    = ["pending","requested","waitlisted","cleared","expired","denied"]
PLAN_ROUTES     = {"free":1, "pro":10, "elite":9999}
PLAN_INTERVAL   = {"free":86400, "pro":28800, "elite":14400}  # seconds between checks


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id                    = db.Column(db.Integer, primary_key=True)
    email                 = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash         = db.Column(db.String(255), nullable=False)
    name                  = db.Column(db.String(120), default="")
    created_at            = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Plan
    plan                  = db.Column(db.String(20), default="free")   # free|pro|elite
    stripe_customer_id    = db.Column(db.String(120), unique=True)
    stripe_subscription_id= db.Column(db.String(120), unique=True)
    subscription_status   = db.Column(db.String(30), default="inactive")
    subscription_end      = db.Column(db.DateTime)

    # Notifications — user can enable any combination
    notify_email          = db.Column(db.Boolean, default=True)
    notify_sms            = db.Column(db.Boolean, default=False)
    notify_whatsapp       = db.Column(db.Boolean, default=False)
    notify_telegram       = db.Column(db.Boolean, default=False)
    alert_email           = db.Column(db.String(255))   # defaults to login email
    phone_number          = db.Column(db.String(30))    # E.164 format e.g. +19725551234
    phone_verified        = db.Column(db.Boolean, default=False)
    telegram_chat_id      = db.Column(db.String(60))
    global_target_price   = db.Column(db.Float, default=3000.0)

    # Relationships
    cash_routes   = db.relationship("CashRoute",  backref="user", lazy=True, cascade="all, delete-orphan")
    award_routes  = db.relationship("AwardRoute", backref="user", lazy=True, cascade="all, delete-orphan")
    swu_logs      = db.relationship("SWULog",     backref="user", lazy=True, cascade="all, delete-orphan")
    price_history = db.relationship("PriceHistory", backref="user", lazy=True, cascade="all, delete-orphan")

    @property
    def route_limit(self):          return PLAN_ROUTES.get(self.plan, 1)
    @property
    def can_award_track(self):      return self.plan in ("pro","elite")
    @property
    def can_swu_track(self):        return self.plan == "elite"
    @property
    def check_interval(self):       return PLAN_INTERVAL.get(self.plan, 86400)
    @property
    def effective_email(self):      return self.alert_email or self.email
    @property
    def any_notify_enabled(self):
        return self.notify_email or self.notify_sms or self.notify_telegram or self.notify_whatsapp


class CashRoute(db.Model):
    __tablename__ = "cash_routes"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    label         = db.Column(db.String(200), nullable=False)
    slices_json   = db.Column(db.Text, nullable=False)
    alliance      = db.Column(db.String(30), default="oneworld")
    airlines_json = db.Column(db.Text, default="[]")
    cabin         = db.Column(db.String(30), default="business")
    target_price  = db.Column(db.Float)
    active        = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_price    = db.Column(db.Float)
    last_route    = db.Column(db.String(500))
    last_checked  = db.Column(db.DateTime)
    last_alerted  = db.Column(db.DateTime)

    @property
    def slices(self):
        import json; return json.loads(self.slices_json)
    @property
    def airlines(self):
        import json; return json.loads(self.airlines_json or "[]")


class AwardRoute(db.Model):
    __tablename__ = "award_routes"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    label         = db.Column(db.String(200), default="")
    origin        = db.Column(db.String(5), nullable=False)
    destination   = db.Column(db.String(5), nullable=False)
    date          = db.Column(db.String(12), nullable=False)
    trip_type     = db.Column(db.String(20), default="one_way")
    cabin         = db.Column(db.String(20), default="business")
    alliance      = db.Column(db.String(30), default="oneworld")
    programs_json = db.Column(db.Text, default="[]")
    max_miles     = db.Column(db.Integer)
    only_direct   = db.Column(db.Boolean, default=False)
    active        = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_miles    = db.Column(db.Integer)
    last_taxes    = db.Column(db.Float)
    last_checked  = db.Column(db.DateTime)
    last_alerted  = db.Column(db.DateTime)

    @property
    def programs(self):
        import json; return json.loads(self.programs_json or "[]")
    @property
    def display_label(self):
        return self.label or f"{self.origin} → {self.destination}"


class SWULog(db.Model):
    __tablename__ = "swu_logs"
    id                   = db.Column(db.Integer, primary_key=True)
    user_id              = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    airline              = db.Column(db.String(5), nullable=False)
    flight_number        = db.Column(db.String(10), nullable=False)
    origin               = db.Column(db.String(5), nullable=False)
    destination          = db.Column(db.String(5), nullable=False)
    flight_date          = db.Column(db.String(12), nullable=False)
    cabin_requested      = db.Column(db.String(20), default="business")
    swu_status           = db.Column(db.String(20), default="pending")
    requested_at         = db.Column(db.DateTime)
    cleared_at           = db.Column(db.DateTime)
    notes                = db.Column(db.Text, default="")
    monitor_award_space  = db.Column(db.Boolean, default=True)
    last_space_available = db.Column(db.Boolean, default=False)
    last_miles           = db.Column(db.Integer)
    last_taxes           = db.Column(db.Float)
    last_checked         = db.Column(db.DateTime)
    last_alerted         = db.Column(db.DateTime)
    created_at           = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def flight_label(self):
        return f"{self.airline}{self.flight_number} {self.origin}→{self.destination} {self.flight_date}"

    @property
    def status_color(self):
        return {"pending":"muted","requested":"blue","waitlisted":"yellow",
                "cleared":"green","expired":"muted","denied":"red"}.get(self.swu_status,"muted")


class PriceHistory(db.Model):
    __tablename__ = "price_history"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    route_id      = db.Column(db.Integer, nullable=False)
    route_type    = db.Column(db.String(10), nullable=False)   # cash|award
    checked_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    price         = db.Column(db.Float)
    miles         = db.Column(db.Integer)
    taxes         = db.Column(db.Float)
    route_detail  = db.Column(db.String(500), default="")
    cabin         = db.Column(db.String(20), default="")
    alliance      = db.Column(db.String(30), default="")
    program       = db.Column(db.String(50), default="")
