#!/usr/bin/env python3
"""
Admin utility — upgrade a user to Elite plan directly in the DB.
Run on Railway via: python admin.py upgrade brian.c.thompson@outlook.com
"""
import sys, os

def upgrade_user(email, plan="elite"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from __init__ import create_app
    from models import db, User

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email=email.lower().strip()).first()
        if not user:
            print(f"No user found with email: {email}")
            return
        old_plan = user.plan
        user.plan = plan
        user.subscription_status = "active"
        db.session.commit()
        print(f"✓ Upgraded {user.email} ({user.name}) from {old_plan} → {plan}")

def list_users():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from __init__ import create_app
    from models import db, User

    app = create_app()
    with app.app_context():
        users = User.query.all()
        print(f"{'Email':<40} {'Name':<20} {'Plan':<10} {'Status'}")
        print("-" * 85)
        for u in users:
            print(f"{u.email:<40} {(u.name or ''):<20} {u.plan:<10} {u.subscription_status}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python admin.py list")
        print("  python admin.py upgrade user@email.com")
        print("  python admin.py upgrade user@email.com pro")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "list":
        list_users()
    elif cmd == "upgrade" and len(sys.argv) >= 3:
        email = sys.argv[2]
        plan  = sys.argv[3] if len(sys.argv) > 3 else "elite"
        upgrade_user(email, plan)
    else:
        print("Unknown command. Use: list | upgrade <email> [plan]")
