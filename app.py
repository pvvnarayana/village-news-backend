from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
import os
import logging
from dotenv import load_dotenv
load_dotenv()

from auth import auth_bp
from video import video_bp

app = Flask(__name__)
# It's best practice to load secrets from environment variables
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "a-super-secret-key-for-dev")
app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID")

# Ensure critical environment variables are set
if not app.config["GOOGLE_CLIENT_ID"]:
    raise ValueError("A GOOGLE_CLIENT_ID environment variable is required.")

# For production, it's crucial to restrict CORS to your frontend's domain.
# Load the allowed origin from an environment variable.
FRONTEND_URL = os.getenv("FRONTEND_URL", "*") # Default to '*' for development if not set

CORS(app, resources={r"/api/*": {"origins": FRONTEND_URL}})
jwt = JWTManager(app)

app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(video_bp, url_prefix="/api")

@app.route("/api/health")
def health():
    return jsonify({"status": "running"})

if __name__ == "__main__":
    # Configure basic logging for the application
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Add a check to prevent running with the default secret in production.
    if not app.debug and app.config["JWT_SECRET_KEY"] == "a-super-secret-key-for-dev":
        raise ValueError("Do not use the default JWT_SECRET_KEY in production.")

    app.run(debug=True)