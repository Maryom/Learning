from datetime import datetime
import json
import os
from flask import Flask, jsonify, request

# Initialize the Flask application
app = Flask(__name__)

# Configuration constants
DATA_FILE = "courses.json"
VALID_STATUSES = ["Not Started", "In Progress", "Completed"]
REQUIRED_FIELDS = ["name", "description", "target_date", "status"]


# ---------------------------------------------------------------------------
# File Storage Helper Functions
# ---------------------------------------------------------------------------


def initialize_storage():
    """Create courses.json with an empty list if it does not already exist."""
    if not os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as file:
                json.dump([], file, indent=4)
        except OSError as error:
            print(f"Warning: Could not create {DATA_FILE}: {error}")


def load_courses():
    """Read and return the list of courses from courses.json.

    Raises IOError/ValueError if the file cannot be read or contains invalid
    JSON.
    """
    initialize_storage()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Failed to read course data: {error}") from error


def save_courses(courses):
    """Write the complete list of courses back to courses.json.

    Raises RuntimeError if writing to disk fails.
    """
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(courses, file, indent=4)
    except OSError as error:
        raise RuntimeError(f"Failed to save course data: {error}") from error


# ---------------------------------------------------------------------------
# Validation Helper Functions
# ---------------------------------------------------------------------------


def is_valid_date(date_string):
    """Verify that target_date is a string matching YYYY-MM-DD."""
    if not isinstance(date_string, str):
        return False
    try:
        datetime.strptime(date_string, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_course_payload(data, is_update=False):
    """Validate incoming JSON data for creating or updating a course.

    Returns an error message string if invalid, or None if valid.
    """
    if not data or not isinstance(data, dict):
        return "Request body must be valid JSON."

    # For POST requests, every required field must be present and non-empty
    if not is_update:
        missing = [
            field for field in REQUIRED_FIELDS if not str(data.get(field, "")).strip()
        ]
        if missing:
            return f"Missing or empty required fields: {', '.join(missing)}"

    # Validate status if provided
    if "status" in data and data["status"] not in VALID_STATUSES:
        return f"Invalid status '{data['status']}'. Must be one of: {', '.join(VALID_STATUSES)}"

    # Validate target_date format if provided
    if "target_date" in data and not is_valid_date(data["target_date"]):
        return "Invalid target_date format. Expected YYYY-MM-DD (e.g., 2026-12-31)."

    # Ensure name and description aren't overwritten with blank strings on PUT
    for text_field in ["name", "description"]:
        if text_field in data and not str(data[text_field]).strip():
            return f"Field '{text_field}' cannot be empty."

    return None


# ---------------------------------------------------------------------------
# Global Error Handlers
# ---------------------------------------------------------------------------


@app.errorhandler(RuntimeError)
def handle_storage_error(error):
    """Return a clean 500 JSON response whenever file read/write fails."""
    return jsonify({"error": str(error)}), 500


@app.errorhandler(404)
def handle_not_found(_error):
    """Return JSON instead of HTML when an unknown URL is requested."""
    return jsonify({"error": "Endpoint not found"}), 404


# ---------------------------------------------------------------------------
# REST API Endpoints
# ---------------------------------------------------------------------------


@app.route("/api/courses", methods=["GET"])
def get_all_courses():
    """GET /api/courses - Retrieve all tracked courses."""
    courses = load_courses()
    return jsonify(courses), 200


@app.route("/api/courses/<int:course_id>", methods=["GET"])
def get_course(course_id):
    """GET /api/courses/<id> - Retrieve a single course by its numeric ID."""
    courses = load_courses()

    # Search for the course matching course_id
    course = next((item for item in courses if item["id"] == course_id), None)
    if course is None:
        return jsonify({"error": f"Course with ID {course_id} not found"}), 404

    return jsonify(course), 200


@app.route("/api/courses", methods=["POST"])
def create_course():
    """POST /api/courses - Add a new course to courses.json."""
    # silent=True prevents Flask from throwing an HTML 400 error on malformed JSON
    data = request.get_json(silent=True)

    validation_error = validate_course_payload(data, is_update=False)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    courses = load_courses()

    # Auto-generate ID starting at 1, incrementing from the highest existing ID
    next_id = max((course["id"] for course in courses), default=0) + 1

    new_course = {
        "id": next_id,
        "name": data["name"].strip(),
        "description": data["description"].strip(),
        "target_date": data["target_date"],
        "status": data["status"],
        # Auto-generated ISO 8601 timestamp (e.g., "2026-11-27T15:00:00")
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    courses.append(new_course)
    save_courses(courses)

    # HTTP 201 Created is standard when a new resource is created
    return jsonify(new_course), 201


@app.route("/api/courses/<int:course_id>", methods=["PUT"])
def update_course(course_id):
    """PUT /api/courses/<id> - Update an existing course's fields."""
    data = request.get_json(silent=True)

    validation_error = validate_course_payload(data, is_update=True)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    courses = load_courses()
    course = next((item for item in courses if item["id"] == course_id), None)

    if course is None:
        return jsonify({"error": f"Course with ID {course_id} not found"}), 404

    # Update only the allowed fields present in the request body
    if "name" in data:
        course["name"] = data["name"].strip()
    if "description" in data:
        course["description"] = data["description"].strip()
    if "target_date" in data:
        course["target_date"] = data["target_date"]
    if "status" in data:
        course["status"] = data["status"]

    save_courses(courses)
    return jsonify(course), 200


@app.route("/api/courses/<int:course_id>", methods=["DELETE"])
def delete_course(course_id):
    """DELETE /api/courses/<id> - Remove a course by its numeric ID."""
    courses = load_courses()

    # Keep all courses except the one matching course_id
    remaining_courses = [item for item in courses if item["id"] != course_id]

    # If the list length did not shrink, the ID did not exist
    if len(remaining_courses) == len(courses):
        return jsonify({"error": f"Course with ID {course_id} not found"}), 404

    save_courses(remaining_courses)
    return jsonify({"message": f"Course {course_id} deleted successfully"}), 200


# Ensure courses.json exists as soon as the app starts
initialize_storage()

if __name__ == "__main__":
    # Run the Flask development server on http://127.0.0.1:5000
    app.run(debug=True, port=5001)