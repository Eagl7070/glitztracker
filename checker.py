#!/usr/bin/env python3
"""
GlitzTracker background checker — works with flat file structure at root level.
"""
import os, sys, json, re, time, logging
from datetime import datetime, timezone, timedelta

import requests

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("checker")

SERPAPI_KEY    = os.environ.get("SERPAPI_KEY", "")
SEATS_AERO_KEY = os.environ.get("SEATS_AERO_API_KEY", "")
LOOP_SLEEP     = int(os.environ.get("CHECKER_SLEEP_SECS", "900"))

ALLIANCE_CODES = {
    "oneworld":     {"AA","BA","IB","AY","QR","JL","QF","CX","MH","S7","UL","RJ","AT","AS","FJ"},
    "skyteam":      {"DL","AF","KL","AM","MU","KE","SU","AZ","CZ","GA","KQ","ME","OK","RO","SV","UX","VN","VS"},
    "staralliance": {"UA","LH","NH","AC","OS","LO","AV","MS","SN","BR","CA","CM","ET","LX","OU","OZ","SA","SK","TG","TP","TK"},
    "any": set(),
}
CABIN_CODES  = {"economy":"1","premium_economy":"2","business":"3","first":"4"}
CABIN_PREFIX = {"economy":"Y","premium_economy":"W","business":"J","first":"F"}
ALLIANCE_PROGS = {
    "oneworld":     ["american","alaska","qantas","british","cathay","finnair","iberia","japan"],
    "skyteam":      ["delta","airfrance","flying_blue","korean","aeromexico"],
    "staralliance": ["united","lufthansa","aeroplan","ana","swiss","avianca","turkish"],
    "any":          ["american","alaska","delta","united","lufthansa","flying_blue","aeroplan",
                     "qantas","british","cathay","finnair","iberia","japan","korean","ana"],
}
CABIN_LABEL = {"economy":"Economy","premium_economy":"Prem Economy","business":"Business","first":"First"}


def carrier_code(fn):
    m = re.match(r"\s*([A-Z0-9]{2})", (fn or "").upper())
    return m.group(1) if m else ""

def passes_filter(opt, allowed):
    if not allowed: return True
    return all(carrier_code(l.get("flight_number","")) in allowed for l in opt.get("flights",[]))

def summarize(opt):
    return " > ".join(
        f"{l.get('departure_airport',{}).get('id','?')}-{l.get('arrival_airport',{}).get('id','?')}({l.get('flight_number','?')})"
        for l in opt.get("flights",[]))

def check_cash(route):
    if not SERPAPI_KEY: return None, None
    slices   = json.loads(route.slices_json)
    airlines = json.loads(route.airlines_json or "[]")
    allowed  = set(airlines) if airlines else ALLIANCE_CODES.get(route.alliance or "oneworld", set())
    cabin    = CABIN_CODES.get(route.cabin or "business","3")
    params   = {"engine":"google_flights","api_key":SERPAPI_KEY,"type":"3",
                "multi_city_json":json.dumps([{"departure_id":s["departure_id"],
                    "arrival_id":s["arrival_id"],"date":s["date"]} for s in slices]),
                "travel_class":cabin,"currency":"USD","hl":"en","gl":"us","deep_search":"true"}
    try:
        r = requests.get("https://serpapi.com/search.json", params=params, timeout=90)
        r.raise_for_status(); data = r.json()
    except Exception as e:
        log.error("SerpApi error route %d: %s", route.id, e); return None, None
    opts     = (data.get("best_flights") or []) + (data.get("other_flights") or [])
    filtered = [o for o in opts if passes_filter(o, allowed)]
    if not filtered: return None, None
    best = min(filtered, key=lambda o: o.get("price",1e9))
    return best.get("price"), summarize(best)

def check_award(route):
    if not SEATS_AERO_KEY: return []
    progs  = json.loads(route.programs_json or "[]") or ALLIANCE_PROGS.get(route.alliance or "oneworld",[])
    prefix = CABIN_PREFIX.get(route.cabin or "business","J")
    params = {"origin_airport":route.origin,"destination_airport":route.destination,
              "cabin":route.cabin or "business","start_date":route.date,"end_date":route.date,
              "take":50,"order_by":"lowest_mileage","sources":",".join(progs)}
    if route.only_direct: params["only_direct_flights"] = "true"
    try:
        r = requests.get("https://seats.aero/partnerapi/search",
            params=params, headers={"Partner-Authorization":SEATS_AERO_KEY,"accept":"application/json"},
            timeout=60)
        if r.status_code == 401: log.error("seats.aero 401"); return []
        r.raise_for_status(); data = r.json()
    except Exception as e:
        log.error("seats.aero error route %d: %s", route.id, e); return []
    out = []
    for item in data.get("data",[]):
        if not item.get(f"{prefix}Available"): continue
        try: miles = int(str(item.get(f"{prefix}MileageCost","0")).replace(",",""))
        except: miles = 0
        if route.max_miles and miles and miles > route.max_miles: continue
        try: taxes = float(str(item.get(f"{prefix}Taxes","0")).replace(",",""))
        except: taxes = 0.0
        out.append({"miles":miles,"taxes":taxes or None,"direct":bool(item.get(f"{prefix}Direct")),
                    "program":item.get("Source","?"),"airlines":item.get(f"{prefix}Airlines","") or ""})
    return out

def check_swu_space(swu):
    if not SEATS_AERO_KEY: return False, None, None
    prefix = CABIN_PREFIX.get(swu.cabin_requested or "business","J")
    params = {"origin_airport":swu.origin,"destination_airport":swu.destination,
              "cabin":swu.cabin_requested or "business","start_date":swu.flight_date,
              "end_date":swu.flight_date,"take":20}
    try:
        r = requests.get("https://seats.aero/partnerapi/search",
            params=params, headers={"Partner-Authorization":SEATS_AERO_KEY,"accept":"application/json"},
            timeout=60)
        r.raise_for_status(); data = r.json()
    except Exception as e:
        log.error("SWU check error %d: %s", swu.id, e); return False, None, None
    for item in data.get("data",[]):
        if not item.get(f"{prefix}Available"): continue
        try: miles = int(str(item.get(f"{prefix}MileageCost","0")).replace(",",""))
        except: miles = 0
        try: taxes = float(str(item.get(f"{prefix}Taxes","0")).replace(",",""))
        except: taxes = None
        return True, miles or None, taxes
    return False, None, None

def alert_ok(last, hours=12):
    if not last: return True
    return (datetime.now(timezone.utc) - last.replace(tzinfo=timezone.utc)).total_seconds() >= hours*3600

def run():
    # Add root dir to path so imports work from flat structure
    root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, root)

    from __init__ import create_app
    from models import db, User, CashRoute, AwardRoute, SWULog, PriceHistory
    from notifier import notify_user

    flask_app = create_app()
    log.info("GlitzTracker checker started.")

    while True:
        try:
            with flask_app.app_context():
                now = datetime.now(timezone.utc)
                for user in User.query.all():
                    interval = user.check_interval

                    for route in user.cash_routes:
                        if not route.active: continue
                        if route.last_checked:
                            if (now - route.last_checked.replace(tzinfo=timezone.utc)).total_seconds() < interval: continue
                        price, detail = check_cash(route)
                        route.last_checked = now
                        if price:
                            route.last_price = price; route.last_route = detail
                            db.session.add(PriceHistory(user_id=user.id,route_id=route.id,
                                route_type="cash",price=price,route_detail=detail,
                                cabin=route.cabin,alliance=route.alliance))
                            target = route.target_price or user.global_target_price
                            if target and price <= target and alert_ok(route.last_alerted):
                                cab = CABIN_LABEL.get(route.cabin,"Business")
                                msg = (f"✈️ FARE ALERT — GlitzTracker\n{route.label}\n"
                                       f"${price:,.0f} (target ${target:,.0f}) · {cab}\n"
                                       f"{detail}\nVerify on Google Flights now.")
                                if notify_user(user, msg, f"Fare Alert ${price:,.0f}"):
                                    route.last_alerted = now
                        db.session.commit()

                    if user.can_award_track:
                        for route in user.award_routes:
                            if not route.active: continue
                            if route.last_checked:
                                if (now - route.last_checked.replace(tzinfo=timezone.utc)).total_seconds() < interval: continue
                            finds = check_award(route)
                            route.last_checked = now
                            if finds:
                                best = min(finds, key=lambda f: f["miles"] or 1e9)
                                route.last_miles = best["miles"]; route.last_taxes = best["taxes"]
                                db.session.add(PriceHistory(user_id=user.id,route_id=route.id,
                                    route_type="award",miles=best["miles"],taxes=best["taxes"],
                                    cabin=route.cabin,alliance=route.alliance,program=best["program"]))
                                if alert_ok(route.last_alerted):
                                    ms = f"{best['miles']:,} mi" if best["miles"] else "available"
                                    tx = f" + ${best['taxes']:.0f} taxes" if best["taxes"] else ""
                                    msg = (f"🎟️ AWARD SPACE — GlitzTracker\n{route.display_label}\n"
                                           f"{ms}{tx} · {best['program']}\nBook fast on program site.")
                                    if notify_user(user, msg, f"Award Space — {route.display_label}"):
                                        route.last_alerted = now
                            db.session.commit()

                    if user.can_swu_track:
                        for swu in user.swu_logs:
                            if not swu.monitor_award_space: continue
                            if swu.swu_status in ("cleared","expired","denied"): continue
                            if swu.last_checked:
                                if (now - swu.last_checked.replace(tzinfo=timezone.utc)).total_seconds() < interval: continue
                            prev = swu.last_space_available
                            available, miles, taxes = check_swu_space(swu)
                            swu.last_checked = now; swu.last_space_available = available
                            if miles: swu.last_miles = miles
                            if taxes: swu.last_taxes = taxes
                            if available and not prev and alert_ok(swu.last_alerted, hours=4):
                                ms = f"{miles:,} mi" if miles else "space open"
                                tx = f" + ${taxes:.0f} taxes" if taxes else ""
                                msg = (f"🔔 SWU SIGNAL — GlitzTracker\n{swu.flight_label}\n"
                                       f"Business award space just opened ({ms}{tx}).\n"
                                       f"Call {swu.airline} elite line NOW.\nSpace disappears fast.")
                                if notify_user(user, msg, f"SWU Opportunity — {swu.flight_label}"):
                                    swu.last_alerted = now
                            db.session.commit()
        except Exception as e:
            log.exception("Checker error: %s", e)
        time.sleep(LOOP_SLEEP)

if __name__ == "__main__":
    run()
