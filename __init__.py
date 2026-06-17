import os
from flask import Flask
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from models import db, User

bcrypt = Bcrypt()
login_manager = LoginManager()


def create_app():
    root = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__,
                template_folder=os.path.join(root, "templates"),
                static_folder=os.path.join(root, "static"))

    app.config.update(
        SECRET_KEY                 = os.environ.get("SECRET_KEY", "dev-change-in-prod"),
        SQLALCHEMY_DATABASE_URI    = os.environ.get("DATABASE_URL", "sqlite:////data/glitztracker.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS = False,
        STRIPE_SECRET_KEY          = os.environ.get("STRIPE_SECRET_KEY",""),
        STRIPE_PUBLISHABLE_KEY     = os.environ.get("STRIPE_PUBLISHABLE_KEY",""),
        STRIPE_WEBHOOK_SECRET      = os.environ.get("STRIPE_WEBHOOK_SECRET",""),
        STRIPE_PRO_PRICE_ID        = os.environ.get("STRIPE_PRO_PRICE_ID",""),
        STRIPE_ELITE_PRICE_ID      = os.environ.get("STRIPE_ELITE_PRICE_ID",""),
        SERPAPI_KEY                = os.environ.get("SERPAPI_KEY",""),
        SEATS_AERO_API_KEY         = os.environ.get("SEATS_AERO_API_KEY",""),
        APP_URL                    = os.environ.get("APP_URL","https://glitztracker.com"),
        SITE_NAME                  = "GlitzTracker",
    )

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view    = "auth.login"
    login_manager.login_message = "Sign in to access your tracker."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(uid):
        return User.query.get(int(uid))

    from routes.public    import public_bp
    from routes.auth      import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.api       import api_bp
    from routes.billing   import billing_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp,       url_prefix="/auth")
    app.register_blueprint(dashboard_bp,  url_prefix="/dashboard")
    app.register_blueprint(api_bp,        url_prefix="/api")
    app.register_blueprint(billing_bp,    url_prefix="/billing")

    with app.app_context():
        db.create_all()

    return app
