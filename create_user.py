#!/usr/bin/env python3
import os, sys
sys.path.insert(0, '/app')

def create_and_upgrade():
    from __init__ import create_app
    from models import db, User
    from flask_bcrypt import Bcrypt

    app = create_app()
    bcrypt = Bcrypt(app)
    
    with app.app_context():
        # Check if user exists
        existing = User.query.filter_by(email='emg@monger.net').first()
        if existing:
            existing.plan = 'elite'
            existing.subscription_status = 'active'
            db.session.commit()
            print(f"Updated existing user {existing.email} to elite")
            return
        
        # Create new user
        hashed = bcrypt.generate_password_hash('BearLovesHoneypot').decode('utf-8')
        user = User(
            email='emg@monger.net',
            name='EMG Monger',
            password_hash=hashed,
            plan='elite',
            subscription_status='active',
            notify_email=True,
        )
        db.session.add(user)
        db.session.commit()
        print(f"Created user: {user.email} | plan: {user.plan}")

if __name__ == '__main__':
    create_and_upgrade()
