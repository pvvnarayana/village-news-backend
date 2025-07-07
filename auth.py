from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from db import get_db
import logging

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["POST"])
def login():
    google_client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    token = request.json.get("id_token")
    try:
        info = id_token.verify_oauth2_token(token, grequests.Request(), google_client_id)
        logging.info(f"Successfully verified Google token for email: {info.get('email')}")
    except ValueError:
        # Invalid token
        return jsonify({"error": "Invalid token"}), 401

    email = info["email"]
    name = info.get("name", email.split("@")[0])
    profile_pic = info.get("picture")

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

    is_new_user = False
    if not user:
        # User does not exist, create a new one with profile info
        logging.info(f"New user detected. Creating profile for {email}.")
        is_new_user = True
        cursor = db.execute(
            "INSERT INTO users (username, email, profile_image, is_admin) VALUES (?, ?, ?, ?)",
            (name, email, profile_pic, 0)
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    else:
        # User exists, update their name and profile picture to keep it fresh
        logging.info(f"Existing user '{email}' logged in. Updating profile info.")
        db.execute("UPDATE users SET username = ?, profile_image = ? WHERE id = ?", (name, profile_pic, user["id"]))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    
    # Record the login event
    ip_address = request.remote_addr
    db.execute("INSERT INTO login_history (user_id, ip_address) VALUES (?, ?)", (user["id"], ip_address))
    db.commit()
    logging.info(f"Recorded login for user ID {user['id']} from IP {ip_address}.")

    # Create JWT with user id as identity and user info as additional claims
    identity = str(user["id"])
    additional_claims = {
        "username": user["username"],
        "email": user["email"],
        "is_admin": user["is_admin"],
        "profile_image": user["profile_image"]
    }
    access_token = create_access_token(identity=identity, additional_claims=additional_claims)
    return jsonify(token=access_token, is_new_user=is_new_user)

@auth_bp.route("/history", methods=["GET"])
@jwt_required()
def history():
    user_id = get_jwt_identity()
    logging.info(f"User ID {user_id} requested their login history.")
    db = get_db()
    history_rows = db.execute(
        "SELECT id, login_timestamp, ip_address FROM login_history WHERE user_id = ? ORDER BY login_timestamp DESC", (user_id,)
    ).fetchall()
    return jsonify([dict(row) for row in history_rows])