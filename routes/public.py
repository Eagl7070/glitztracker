from flask import Blueprint, render_template
public_bp = Blueprint("public", __name__)

@public_bp.route("/")
def index():
    return render_template("public/index.html")

@public_bp.route("/pricing")
def pricing():
    return render_template("public/pricing.html")

@public_bp.route("/how-it-works")
def how_it_works():
    return render_template("public/how_it_works.html")
