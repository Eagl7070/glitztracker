import json
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import db, CashRoute, AwardRoute, PriceHistory

api_bp = Blueprint("api", __name__)

ALLIANCE_CODES = {
    "oneworld":     {"AA","BA","IB","AY","QR","JL","QF","CX","MH","S7","UL","RJ","AT","AS","FJ"},
    "skyteam":      {"DL","AF","KL","AM","MU","KE","SU","AZ","CZ","GA","KQ","ME","OK","RO","SV","UX","VN","VS"},
    "staralliance": {"UA","LH","NH","AC","OS","LO","AV","MS","SN","BR","CA","CM","ET","LX","OU","OZ","SA","SK","TG","TP","TK"},
    "any": set(),
}


def _cash_dict(r):
    return {"id":r.id,"label":r.label,"slices":r.slices,"alliance":r.alliance,
            "airlines":r.airlines,"cabin":r.cabin,"target_price":r.target_price,
            "last_price":r.last_price,"last_route":r.last_route,
            "last_checked":r.last_checked.isoformat() if r.last_checked else None}

def _award_dict(r):
    return {"id":r.id,"label":r.display_label,"origin":r.origin,"destination":r.destination,
            "date":r.date,"trip_type":r.trip_type,"cabin":r.cabin,"alliance":r.alliance,
            "programs":r.programs,"max_miles":r.max_miles,"only_direct":r.only_direct,
            "last_miles":r.last_miles,"last_taxes":r.last_taxes,
            "last_checked":r.last_checked.isoformat() if r.last_checked else None}


@api_bp.route("/cash/routes")
@login_required
def cash_routes():
    return jsonify([_cash_dict(r) for r in current_user.cash_routes])


@api_bp.route("/cash/routes", methods=["POST"])
@login_required
def add_cash_route():
    if len(current_user.cash_routes) >= current_user.route_limit:
        return jsonify({"error":f"Your {current_user.plan} plan allows {current_user.route_limit} route(s). Upgrade for more."}), 403
    b = request.json or {}
    if not b.get("label") or not b.get("slices"):
        return jsonify({"error":"label and slices required"}), 400
    r = CashRoute(
        user_id       = current_user.id,
        label         = b["label"].strip(),
        slices_json   = json.dumps(b["slices"]),
        alliance      = b.get("alliance","oneworld"),
        airlines_json = json.dumps([a.upper().strip() for a in b.get("airlines",[]) if a.strip()]),
        cabin         = b.get("cabin","business"),
        target_price  = b.get("target_price") or current_user.global_target_price,
    )
    db.session.add(r); db.session.commit()
    return jsonify(_cash_dict(r))


@api_bp.route("/cash/routes/<int:rid>", methods=["DELETE"])
@login_required
def del_cash_route(rid):
    r = CashRoute.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
    db.session.delete(r); db.session.commit()
    return jsonify({"deleted":rid})


@api_bp.route("/cash/target", methods=["POST"])
@login_required
def set_target():
    """Set global target (legacy) or per-route target."""
    body = request.json or {}
    route_id = body.get("route_id")
    try: t = float(body["target_price"])
    except: return jsonify({"error":"target_price required"}), 400
    if route_id:
        route = CashRoute.query.filter_by(id=route_id, user_id=current_user.id).first_or_404()
        route.target_price = t
        db.session.commit()
        return jsonify({"route_id": route_id, "target_price": t})
    # Global fallback
    current_user.global_target_price = t
    CashRoute.query.filter_by(user_id=current_user.id).update({"target_price":t})
    db.session.commit()
    return jsonify({"target_price": t})


@api_bp.route("/award/routes/<int:rid>/target", methods=["POST"])
@login_required
def set_award_target(rid):
    """Set per-award-route miles target."""
    route = AwardRoute.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
    body = request.json or {}
    try: miles = int(body["max_miles"])
    except: return jsonify({"error":"max_miles required"}), 400
    route.max_miles = miles
    db.session.commit()
    return jsonify({"route_id": rid, "max_miles": miles})


@api_bp.route("/award/routes")
@login_required
def award_routes():
    return jsonify([_award_dict(r) for r in current_user.award_routes])


@api_bp.route("/award/routes", methods=["POST"])
@login_required
def add_award_route():
    if not current_user.can_award_track:
        return jsonify({"error":"Award tracking requires Pro or Elite. Upgrade to unlock."}), 403
    b = request.json or {}
    for k in ("origin","destination","date"):
        if not b.get(k): return jsonify({"error":f"{k} required"}), 400
    r = AwardRoute(
        user_id       = current_user.id,
        label         = b.get("label","").strip(),
        origin        = b["origin"].upper().strip(),
        destination   = b["destination"].upper().strip(),
        date          = b["date"].strip(),
        trip_type     = b.get("trip_type","one_way"),
        cabin         = b.get("cabin","business"),
        alliance      = b.get("alliance","oneworld"),
        programs_json = json.dumps([p.strip().lower() for p in b.get("programs",[]) if p.strip()]),
        max_miles     = b.get("max_miles") or None,
        only_direct   = bool(b.get("only_direct",False)),
    )
    db.session.add(r); db.session.commit()
    return jsonify(_award_dict(r))


@api_bp.route("/award/routes/<int:rid>", methods=["DELETE"])
@login_required
def del_award_route(rid):
    r = AwardRoute.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
    db.session.delete(r); db.session.commit()
    return jsonify({"deleted":rid})


@api_bp.route("/history")
@login_required
def history():
    rows = PriceHistory.query.filter_by(user_id=current_user.id)\
        .order_by(PriceHistory.checked_at.asc()).limit(500).all()
    return jsonify([{"checked_at":r.checked_at.isoformat(),"route_id":r.route_id,
        "route_type":r.route_type,"price":r.price,"miles":r.miles,"taxes":r.taxes,
        "route_detail":r.route_detail,"cabin":r.cabin,"alliance":r.alliance,
        "program":r.program} for r in rows])
