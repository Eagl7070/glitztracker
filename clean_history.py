#!/usr/bin/env python3
"""Remove price history entries that don't match any existing route."""
import sys
sys.path.insert(0, '/app')
from __init__ import create_app
from models import db, CashRoute, AwardRoute, PriceHistory

app = create_app()
with app.app_context():
    valid_cash_ids  = {r.id for r in CashRoute.query.all()}
    valid_award_ids = {r.id for r in AwardRoute.query.all()}
    
    stale = PriceHistory.query.filter(
        ((PriceHistory.route_type=='cash')  & (~PriceHistory.route_id.in_(valid_cash_ids  or {-1}))) |
        ((PriceHistory.route_type=='award') & (~PriceHistory.route_id.in_(valid_award_ids or {-1})))
    ).all()
    
    print(f"Found {len(stale)} stale history records")
    for h in stale:
        print(f"  Removing: {h.route_type} route_id={h.route_id} price={h.price} detail={h.route_detail}")
        db.session.delete(h)
    
    db.session.commit()
    print(f"Done. Remaining history: {PriceHistory.query.count()} records")
