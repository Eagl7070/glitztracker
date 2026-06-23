import json
from flask import Blueprint, jsonify, request, current_app
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


# ── Calendar endpoints ────────────────────────────────────────────────────────
@api_bp.route("/calendar/cash", methods=["POST"])
@login_required
def calendar_cash():
    """Cash fares for each day in a month via SerpApi Google Flights price insights."""
    import requests as req
    from datetime import date, timedelta
    body = request.json or {}
    origin      = body.get("origin","").upper().strip()
    destination = body.get("destination","").upper().strip()
    cabin       = body.get("cabin","business")
    start_date  = body.get("start_date","")
    end_date    = body.get("end_date","")
    if not all([origin, destination, start_date, end_date]):
        return jsonify({"error":"origin, destination required"}), 400

    SERPAPI_KEY = current_app.config.get("SERPAPI_KEY","")
    if not SERPAPI_KEY:
        return jsonify({"error":"SerpApi not configured"}), 503

    CABIN_CODES = {"economy":"1","premium_economy":"2","business":"3","first":"4"}
    cabin_code  = CABIN_CODES.get(cabin,"3")

    try:
        d_start = date.fromisoformat(start_date)
        d_end   = date.fromisoformat(end_date)
    except Exception:
        return jsonify({"error":"invalid date format"}), 400

    today = date.today()
    results = []

    # Query each day. To stay within SerpApi limits, sample every OTHER day
    # for months far out, every day for near-term. Cap at ~16 calls.
    days = []
    d = max(d_start, today)
    while d <= d_end:
        days.append(d)
        d += timedelta(days=1)

    # If too many days, sample to keep under ~16 API calls
    if len(days) > 16:
        step = len(days) // 16 + 1
        days = days[::step]

    for day in days:
        params = {
            "engine":        "google_flights",
            "api_key":       SERPAPI_KEY,
            "departure_id":  origin,
            "arrival_id":    destination,
            "outbound_date": day.isoformat(),
            "travel_class":  cabin_code,
            "type":          "2",   # one-way
            "currency":      "USD",
            "hl":            "en",
            "gl":            "us",
        }
        try:
            r = req.get("https://serpapi.com/search.json", params=params, timeout=60)
            if r.status_code != 200:
                continue
            data = r.json()
            opts = (data.get("best_flights") or []) + (data.get("other_flights") or [])
            prices = [o.get("price") for o in opts if o.get("price")]
            if prices:
                best_opt = min(opts, key=lambda o: o.get("price", 1e9))
                airline = best_opt.get("flights",[{}])[0].get("airline","")
                results.append({
                    "date": day.isoformat(),
                    "price": min(prices),
                    "airline": airline,
                })
        except Exception as e:
            current_app.logger.error("Calendar cash %s: %s", day, e)
            continue

    return jsonify({"results": results, "origin": origin, "destination": destination})


@api_bp.route("/calendar/award", methods=["POST"])
@login_required
def calendar_award():
    """Award space per day via seats.aero cached availability (Pro-tier endpoint)."""
    import requests as req
    body = request.json or {}
    origin      = body.get("origin","").upper().strip()
    destination = body.get("destination","").upper().strip()
    cabin       = body.get("cabin","business")
    start_date  = body.get("start_date","")
    end_date    = body.get("end_date","")
    programs    = body.get("programs",[])
    if not all([origin, destination, start_date, end_date]):
        return jsonify({"error":"origin, destination, start_date, end_date required"}), 400

    SEATS_KEY = current_app.config.get("SEATS_AERO_API_KEY","")
    if not SEATS_KEY:
        return jsonify({"error":"seats.aero not configured"}), 503

    CABIN_PREFIX = {"economy":"Y","premium_economy":"W","business":"J","first":"F"}
    prefix = CABIN_PREFIX.get(cabin,"J")

    if not programs:
        programs = ["american","alaska","qantas","delta","united","lufthansa",
                    "flying_blue","aeroplan","british","cathay","finnair",
                    "iberia","japan","korean","ana","singapore"]

    headers = {"Partner-Authorization": SEATS_KEY, "accept": "application/json"}
    date_map = {}

    # Query cached availability per program (cap programs to respect daily limit)
    for prog in programs[:8]:
        params = {
            "source":         prog,
            "cabin":          cabin,
            "origin_airport": origin,
            "take":           500,
            "order_by":       "lowest_mileage",
        }
        try:
            r = req.get("https://seats.aero/partnerapi/availability",
                        params=params, headers=headers, timeout=45)
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception as e:
            current_app.logger.error("Award cal %s: %s", prog, e)
            continue

        for item in data.get("data", []):
            # Filter to our destination and date window
            dest_ap = item.get("Route",{}).get("DestinationAirport","") or item.get("DestinationAirport","")
            if dest_ap != destination: continue
            dep_date = item.get("Date","")[:10]
            if not dep_date or dep_date < start_date or dep_date > end_date: continue
            if not item.get(f"{prefix}Available"): continue
            try:   miles = int(str(item.get(f"{prefix}MileageCost","0")).replace(",",""))
            except: miles = 0
            if not miles: continue
            try:   taxes = float(str(item.get(f"{prefix}TotalTaxes","0")).replace(",",""))
            except: taxes = 0.0
            if dep_date not in date_map or miles < date_map[dep_date]["miles"]:
                date_map[dep_date] = {"miles": miles, "taxes": taxes or None, "program": prog}

    results = [{"date":k,"miles":v["miles"],"taxes":v["taxes"],"program":v["program"]}
               for k,v in sorted(date_map.items())]

    return jsonify({"results": results, "origin": origin, "destination": destination})


@api_bp.route("/run/cash", methods=["POST"])
@login_required
def run_cash_now():
    """Trigger an immediate cash fare check for the current user in a background thread."""
    import threading, os, sys, json, re, requests as req
    from datetime import datetime, timezone

    def do_check():
        try:
            SERPAPI_KEY = current_app.config.get("SERPAPI_KEY","")
            if not SERPAPI_KEY:
                return
            CABIN_CODES = {"economy":"1","premium_economy":"2","business":"3","first":"4"}
            ALLIANCE_CODES = {
                "oneworld":     {"AA","BA","IB","AY","QR","JL","QF","CX","MH","S7","UL","RJ","AT","AS","FJ"},
                "skyteam":      {"DL","AF","KL","AM","MU","KE","SU","AZ","CZ","GA","KQ","ME","OK","RO","SV","UX","VN","VS"},
                "staralliance": {"UA","LH","NH","AC","OS","LO","AV","MS","SN","BR","CA","CM","ET","LX","OU","OZ","SA","SK","TG","TP","TK"},
                "any": set(),
            }
            with current_app.app_context():
                from models import db, CashRoute, PriceHistory
                routes = CashRoute.query.filter_by(user_id=current_user.id, active=True).all()
                now = datetime.now(timezone.utc)
                for route in routes:
                    slices = json.loads(route.slices_json)
                    airlines = json.loads(route.airlines_json or "[]")
                    allowed = set(airlines) if airlines else ALLIANCE_CODES.get(route.alliance or "oneworld", set())
                    cabin = CABIN_CODES.get(route.cabin or "business","3")
                    params = {"engine":"google_flights","api_key":SERPAPI_KEY,"type":"3",
                              "multi_city_json":json.dumps([{"departure_id":s["departure_id"],
                                  "arrival_id":s["arrival_id"],"date":s["date"]} for s in slices]),
                              "travel_class":cabin,"currency":"USD","hl":"en","gl":"us","deep_search":"true"}
                    try:
                        r = req.get("https://serpapi.com/search.json", params=params, timeout=90)
                        r.raise_for_status()
                        data = r.json()
                        opts = (data.get("best_flights") or []) + (data.get("other_flights") or [])
                        def passes(opt):
                            if not allowed: return True
                            return all(re.match(r"[A-Z0-9]{2}", l.get("flight_number","")[:2]) and
                                      (l.get("flight_number","")[:2] in allowed) for l in opt.get("flights",[]))
                        filtered = [o for o in opts if passes(o)]
                        if filtered:
                            best = min(filtered, key=lambda o: o.get("price",1e9))
                            price = best.get("price")
                            detail = " > ".join(
                                f"{l.get('departure_airport',{}).get('id','?')}-{l.get('arrival_airport',{}).get('id','?')}({l.get('flight_number','?')})"
                                for l in best.get("flights",[]))
                            route.last_price = price
                            route.last_route = detail
                            route.last_checked = now
                            ph = PriceHistory(user_id=current_user.id, route_id=route.id,
                                route_type="cash", price=price, route_detail=detail,
                                cabin=route.cabin, alliance=route.alliance)
                            db.session.add(ph)
                            db.session.commit()
                    except Exception as e:
                        current_app.logger.error("Manual check error route %d: %s", route.id, e)
        except Exception as e:
            current_app.logger.error("Manual check thread error: %s", e)

    thread = threading.Thread(target=do_check, daemon=True)
    thread.start()
    return jsonify({"status": "check started", "message": "Results will update in ~30 seconds"})


@api_bp.route("/run/award", methods=["POST"])
@login_required
def run_award_now():
    """Trigger an immediate award check for current user."""
    import threading, requests as req
    from datetime import datetime, timezone

    def do_check():
        try:
            SEATS_KEY = current_app.config.get("SEATS_AERO_API_KEY","")
            if not SEATS_KEY:
                return
            CABIN_PREFIX = {"economy":"Y","premium_economy":"W","business":"J","first":"F"}
            with current_app.app_context():
                from models import db, AwardRoute, PriceHistory
                routes = AwardRoute.query.filter_by(user_id=current_user.id, active=True).all()
                now = datetime.now(timezone.utc)
                for route in routes:
                    prefix = CABIN_PREFIX.get(route.cabin or "business","J")
                    progs = json.loads(route.programs_json or "[]")
                    if not progs:
                        progs = ["american","alaska","qantas","delta","united","lufthansa",
                                 "flying_blue","aeroplan","british","cathay","finnair","iberia","japan"]
                    best = None
                    for prog in progs[:6]:
                        params = {"source":prog,"origin_airport":route.origin,
                                  "cabin":route.cabin or "business","take":200,
                                  "order_by":"lowest_mileage"}
                        try:
                            r = req.get("https://seats.aero/partnerapi/availability",
                                params=params, headers={"Partner-Authorization":SEATS_KEY,"accept":"application/json"},
                                timeout=45)
                            if r.status_code != 200: continue
                            data = r.json()
                            for item in data.get("data",[]):
                                dest_ap = item.get("Route",{}).get("DestinationAirport","") or item.get("DestinationAirport","")
                                if dest_ap != route.destination: continue
                                if item.get("Date","")[:10] != route.date: continue
                                if not item.get(f"{prefix}Available"): continue
                                try: miles = int(str(item.get(f"{prefix}MileageCost","0")).replace(",",""))
                                except: miles = 0
                                if not miles: continue
                                if route.max_miles and miles > route.max_miles: continue
                                try: taxes = float(str(item.get(f"{prefix}TotalTaxes","0")).replace(",",""))
                                except: taxes = 0.0
                                if best is None or miles < best["miles"]:
                                    best = {"miles":miles,"taxes":taxes or None,"program":prog}
                        except Exception as e:
                            current_app.logger.error("Manual award check %s route %d: %s", prog, route.id, e)
                    if best:
                        route.last_miles = best["miles"]
                        route.last_taxes = best["taxes"]
                        route.last_checked = now
                        ph = PriceHistory(user_id=current_user.id, route_id=route.id,
                            route_type="award", miles=best["miles"], taxes=best["taxes"],
                            cabin=route.cabin, alliance=route.alliance,
                            program=best["program"])
                        db.session.add(ph)
                        db.session.commit()
        except Exception as e:
            current_app.logger.error("Manual award check thread error: %s", e)

    thread = threading.Thread(target=do_check, daemon=True)
    thread.start()
    return jsonify({"status": "check started"})


@api_bp.route("/explore", methods=["POST"])
@login_required
def explore_deals():
    """Find award deals from an origin or region via seats.aero Bulk Availability."""
    import requests as req
    body = request.json or {}
    origin   = body.get("origin","").upper().strip()
    cabin    = body.get("cabin","business")
    max_pts  = body.get("max_miles")
    programs = body.get("programs",[])
    region   = body.get("region","")

    SEATS_KEY = current_app.config.get("SEATS_AERO_API_KEY","")
    if not SEATS_KEY:
        return jsonify({"error":"seats.aero not configured — add SEATS_AERO_API_KEY"}), 503

    CABIN_PREFIX = {"economy":"Y","premium_economy":"W","business":"J","first":"F"}
    prefix = CABIN_PREFIX.get(cabin,"J")

    if not programs:
        programs = ["american","alaska","united","aeroplan","delta","flying_blue",
                    "british","cathay","lifemiles","virginatlantic","velocity",
                    "qantas","singapore","ana","emirates","etihad","smiles","azul"]

    headers = {"Partner-Authorization": SEATS_KEY, "accept":"application/json"}
    all_deals = []

    # Query a few programs via Bulk Availability
    for prog in programs[:6]:  # cap to stay within daily limits
        params = {"source": prog, "cabin": cabin, "take": 200,
                  "order_by": "lowest_mileage"}
        if origin:
            params["origin_airport"] = origin
        try:
            r = req.get("https://seats.aero/partnerapi/availability",
                        params=params, headers=headers, timeout=40)
            if r.status_code != 200:
                continue
            data = r.json()
            for item in data.get("data", []):
                if not item.get(f"{prefix}Available"): continue
                try:    miles = int(str(item.get(f"{prefix}MileageCost","0")).replace(",",""))
                except: miles = 0
                if not miles: continue
                if max_pts and miles > int(max_pts): continue
                try:    taxes = float(str(item.get(f"{prefix}TotalTaxes","0")).replace(",",""))
                except: taxes = 0.0
                all_deals.append({
                    "origin":      item.get("Route",{}).get("OriginAirport","") or item.get("OriginAirport",""),
                    "destination": item.get("Route",{}).get("DestinationAirport","") or item.get("DestinationAirport",""),
                    "miles":       miles,
                    "taxes":       round(taxes,2) if taxes else None,
                    "date":        item.get("Date","")[:10],
                    "program":     item.get("Source", prog),
                    "cabin":       cabin,
                })
        except Exception as e:
            current_app.logger.error("Explore error %s: %s", prog, e)
            continue

    # Sort by miles, dedupe by route+date
    seen = set()
    unique = []
    for d in sorted(all_deals, key=lambda x: x["miles"]):
        key = (d["origin"], d["destination"], d["date"])
        if key in seen: continue
        seen.add(key)
        unique.append(d)

    return jsonify({"deals": unique[:60], "count": len(unique)})
