from flask import Blueprint, jsonify, current_app, send_from_directory, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from db import get_db
import os
import logging
import uuid
import re
from flask import send_file , Response

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

video_bp = Blueprint("video", __name__)

# This endpoint serves the video files themselves.
# In a production app, you would use a dedicated file server like Nginx or a CDN.
@video_bp.route("/uploads/<path:filename>")
def serve_video(filename):
    logging.info(f"Serving video file: {filename}")
    # Assumes an 'uploads' directory exists in your backend's root folder.
    upload_folder = os.path.join(current_app.root_path, '../uploads')
    return send_from_directory(upload_folder, filename)

@video_bp.route("/videos", methods=["GET"])
def get_videos():
    """Fetches all approved videos to display on the home page."""
    logging.info("Fetching list of approved videos for home page.")
    db = get_db()
    videos = db.execute(
        """
        SELECT v.id, v.title, v.description, v.filename, u.username as uploader
        FROM videos v JOIN users u ON v.user_id = u.id
        WHERE v.status = 'approved'
        ORDER BY v.uploaded_at DESC
        """
    ).fetchall()
    
    # The frontend will construct the full URL for the video files
    return jsonify([dict(row) for row in videos])

@video_bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_video():
    user_id = get_jwt_identity()

    if 'video' not in request.files:
        return jsonify({"error": "No video file part"}), 400
    
    file = request.files['video']
    title = request.form.get('title')

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
    logging.info(f"Upload attempt by user ID {user_id} for video titled '{title}'.")

    if file and allowed_file(file.filename):
        # Secure the filename and make it unique to prevent overwrites
        original_filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{original_filename}"
        
        # Use a path relative to the app's root for portability
        upload_folder = os.path.join(current_app.root_path, '../uploads')
        os.makedirs(upload_folder, exist_ok=True)
        
        file_path = os.path.join(upload_folder, unique_filename)
        logging.info(f"Saving file to: {file_path}")
        file.save(file_path)

        # Save video metadata to the database with a 'pending' status
        description = request.form.get('description', '')
        db = get_db()
        db.execute(
            "INSERT INTO videos (title, description, filename, user_id, status) VALUES (?, ?, ?, ?, 'pending')",
            (title, description, unique_filename, user_id)
        )
        db.commit()
        logging.info(f"Successfully saved video metadata for '{unique_filename}' to database.")

        return jsonify({"message": "Video uploaded successfully and is awaiting approval."}), 201

    logging.warning(f"Upload failed for user ID {user_id}. Invalid file type: {file.filename}")
    return jsonify({"error": "Invalid file type. Please upload a valid video file."}), 400

@video_bp.route("/my-videos", methods=["GET"])
@jwt_required()
def get_my_videos():
    """Fetches all videos uploaded by the current user."""
    user_id = get_jwt_identity()
    logging.info(f"User ID {user_id} requested their uploaded videos.")
    db = get_db()
    videos = db.execute(
        """
        SELECT id, title, description, filename, status, uploaded_at
        FROM videos
        WHERE user_id = ?
        ORDER BY uploaded_at DESC
        """,
        (user_id,)
    ).fetchall()
    return jsonify([dict(row) for row in videos])

@video_bp.route("/videos/<int:video_id>", methods=["DELETE"])
@jwt_required()
def delete_video(video_id):
    user_id = get_jwt_identity()
    db = get_db()

    # Find the video and ensure the current user is the owner
    video = db.execute(
        "SELECT * FROM videos WHERE id = ? AND user_id = ?", (video_id, user_id)
    ).fetchone()

    if not video:
        # Return 404 to avoid leaking information about video existence to non-owners
        logging.warning(f"Failed delete attempt for video ID {video_id} by user ID {user_id}. Video not found or user is not owner.")
        return jsonify({"error": "Video not found or you do not have permission to delete it."}), 404

    try:
        # Delete the physical file from the 'uploads' folder
        filename = video['filename']
        file_path = os.path.join(current_app.root_path, '../uploads', filename)
        import time
        import errno

        if os.path.exists(file_path):
            for attempt in range(3):
                try:
                    os.remove(file_path)
                    logging.info(f"Successfully deleted video file: {file_path}")
                    break
                except PermissionError as e:
                    if hasattr(e, 'winerror') and e.winerror == 32:
                        logging.warning(f"File {file_path} is in use. Attempt {attempt+1}/3. Retrying in 0.5s...")
                        time.sleep(0.5)
                    else:
                        raise
            else:
                logging.error(f"Failed to delete {file_path} after multiple attempts due to file being in use.")
                return jsonify({"error": "File is currently in use and cannot be deleted. Please try again later."}), 423

        # Delete the record from the database
        db.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        db.commit()
        logging.info(f"Successfully deleted video record ID {video_id} from database.")

        return jsonify({"message": "Video deleted successfully."}), 200
    except Exception as e:
        logging.error(f"Error deleting video ID {video_id}: {e}")
        return jsonify({"error": "An internal error occurred while deleting the video."}), 500
    
# The route path should start with a '/' to be relative to the blueprint prefix.
# Removed @jwt_required() to allow public streaming for the home page.
@video_bp.route('/videos/stream/<filename>')
def stream_video(filename):
    # Use a relative path from the app's root to ensure portability.
    upload_folder = os.path.join(current_app.root_path, '../uploads')
    path = os.path.join(upload_folder, filename)
    if not os.path.exists(path):
        return "File not found", 404

    range_header = request.headers.get('Range', None)
    if not range_header:
        return send_file(path, mimetype="video/mp4")

    size = os.path.getsize(path)
    byte1, byte2 = 0, None

    match = re.search(r"bytes=(\d+)-(\d*)", range_header)
    if match:
        g = match.groups()
        byte1 = int(g[0])
        if g[1]:
            byte2 = int(g[1])

    length = size - byte1 if byte2 is None else byte2 - byte1 + 1
    with open(path, 'rb') as f:
        f.seek(byte1)
        data = f.read(length)

    resp = Response(data, 206, mimetype='video/mp4', direct_passthrough=True)
    resp.headers.add('Content-Range', f'bytes {byte1}-{byte1 + length - 1}/{size}')
    resp.headers.add('Accept-Ranges', 'bytes')
    return resp