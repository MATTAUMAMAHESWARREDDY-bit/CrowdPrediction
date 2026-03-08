from flask import Flask, request, jsonify, send_file
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)

RENDER_DISK_PATH = os.environ.get("RENDER_DISK_PATH", ".")
DB = os.path.join(RENDER_DISK_PATH, "database.db")
UPLOAD_FOLDER = os.path.join(RENDER_DISK_PATH, "datasets")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ------------------ DATABASE ------------------

def get_db():
    return sqlite3.connect(DB, check_same_thread=False)


def init_db():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS temples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temple TEXT UNIQUE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS festivals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temple TEXT,
        festival TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS data_limits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temple TEXT,
        festival TEXT,
        low_limit INTEGER,
        medium_limit INTEGER,
        high_limit INTEGER,
        dataset TEXT,
        updated_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temple TEXT,
        festival TEXT,
        email TEXT,
        comment TEXT,
        time TEXT
    )
    """)

    con.commit()

    # old database support: add temple/festival columns if old comments table exists
    cur.execute("PRAGMA table_info(comments)")
    columns = [row[1] for row in cur.fetchall()]

    if "temple" not in columns:
        try:
            cur.execute("ALTER TABLE comments ADD COLUMN temple TEXT")
            con.commit()
        except Exception:
            pass

    if "festival" not in columns:
        try:
            cur.execute("ALTER TABLE comments ADD COLUMN festival TEXT")
            con.commit()
        except Exception:
            pass

    con.close()


init_db()


# ------------------ HELPERS ------------------

def json_error(message, code=400):
    return jsonify({"message": message}), code


def get_risk(count, low, medium, high):
    if count <= low:
        return "Low"
    elif count <= medium:
        return "Medium"
    else:
        return "High"


# ------------------ ROUTES ------------------

@app.route("/")
def home():
    return send_file("index.html")


# ------------------ ADMIN LOGIN ------------------

@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}

    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if username == "mahi" and password == "mahi4248":
        return jsonify({"status": "success"})

    return jsonify({"status": "fail"})


# ------------------ TEMPLE ------------------

@app.route("/add-temple", methods=["POST"])
def add_temple():
    temple = request.form.get("temple", "").strip()

    if not temple:
        return json_error("Temple name is required")

    con = get_db()
    cur = con.cursor()

    try:
        cur.execute("INSERT INTO temples (temple) VALUES (?)", (temple,))
        con.commit()
    except sqlite3.IntegrityError:
        con.close()
        return jsonify({"message": "Temple already exists"})

    con.close()
    return jsonify({"message": "Temple added"})


@app.route("/temples", methods=["GET"])
def get_temples():
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT temple FROM temples ORDER BY temple ASC")
    rows = cur.fetchall()
    con.close()

    return jsonify([r[0] for r in rows])


# ------------------ FESTIVAL ------------------

@app.route("/add-festival", methods=["POST"])
def add_festival():
    temple = request.form.get("temple", "").strip()
    festival = request.form.get("festival", "").strip()

    if not temple or temple == "Select Temple":
        return json_error("Temple is required")

    if not festival:
        return json_error("Festival is required")

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT id FROM temples WHERE temple = ?", (temple,))
    temple_row = cur.fetchone()
    if not temple_row:
        con.close()
        return json_error("Selected temple does not exist")

    cur.execute(
        "SELECT id FROM festivals WHERE temple = ? AND festival = ?",
        (temple, festival)
    )
    exists = cur.fetchone()
    if exists:
        con.close()
        return jsonify({"message": "Festival already exists for this temple"})

    cur.execute(
        "INSERT INTO festivals (temple, festival) VALUES (?, ?)",
        (temple, festival)
    )
    con.commit()
    con.close()

    return jsonify({"message": "Festival added"})


@app.route("/festivals", methods=["GET"])
def get_festivals():
    temple = request.args.get("temple", "").strip()

    con = get_db()
    cur = con.cursor()

    if temple:
        cur.execute(
            "SELECT festival FROM festivals WHERE temple = ? ORDER BY festival ASC",
            (temple,)
        )
        rows = cur.fetchall()
        con.close()
        return jsonify([r[0] for r in rows])

    cur.execute("SELECT temple, festival FROM festivals ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()

    return jsonify([{"temple": r[0], "festival": r[1]} for r in rows])


@app.route("/delete-festival", methods=["DELETE"])
def delete_festival():
    temple = request.args.get("temple", "").strip()
    festival = request.args.get("festival", "").strip()

    if not temple or not festival:
        return json_error("Temple and festival are required")

    con = get_db()
    cur = con.cursor()

    cur.execute(
        "DELETE FROM festivals WHERE temple = ? AND festival = ?",
        (temple, festival)
    )
    deleted = cur.rowcount

    cur.execute(
        "DELETE FROM data_limits WHERE temple = ? AND festival = ?",
        (temple, festival)
    )

    cur.execute(
        "DELETE FROM comments WHERE temple = ? AND festival = ?",
        (temple, festival)
    )

    con.commit()
    con.close()

    if deleted == 0:
        return json_error("Festival not found", 404)

    return jsonify({"message": "Festival deleted"})


# ------------------ DATA + LIMITS ------------------

@app.route("/add-data", methods=["POST"])
def add_data():
    temple = request.form.get("temple", "").strip()
    festival = request.form.get("festival", "").strip()

    if not temple or temple == "Select Temple":
        return json_error("Please select a temple")

    if not festival or festival == "Select Festival":
        return json_error("Please select a festival")

    try:
        low = int(request.form.get("low", "0"))
        medium = int(request.form.get("medium", "0"))
        high = int(request.form.get("high", "0"))
    except ValueError:
        return json_error("Limits must be numbers")

    if low < 0 or medium < 0 or high < 0:
        return json_error("Limits must be positive")

    if not (low <= medium <= high):
        return json_error("Limits must satisfy Low <= Medium <= High")

    if "dataset" not in request.files:
        return json_error("Dataset file required")

    file = request.files["dataset"]
    if not file or file.filename.strip() == "":
        return json_error("Invalid dataset filename")

    safe_name = (
        file.filename
        .replace("\\", "_")
        .replace("/", "_")
        .replace("..", "_")
    )

    unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    path = os.path.join(UPLOAD_FOLDER, unique_name)
    file.save(path)

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    con = get_db()
    cur = con.cursor()

    cur.execute(
        "SELECT id FROM festivals WHERE temple = ? AND festival = ?",
        (temple, festival)
    )
    exists = cur.fetchone()
    if not exists:
        con.close()
        return json_error("Festival not found for selected temple")

    cur.execute(
        "DELETE FROM data_limits WHERE temple = ? AND festival = ?",
        (temple, festival)
    )

    cur.execute("""
        INSERT INTO data_limits
        (temple, festival, low_limit, medium_limit, high_limit, dataset, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (temple, festival, low, medium, high, path, updated_at))

    con.commit()
    con.close()

    return jsonify({"message": "Data saved"})


# ------------------ CROWD ------------------

@app.route("/crowd", methods=["GET"])
def crowd_status():
    temple = request.args.get("temple", "").strip()
    festival = request.args.get("festival", "").strip()

    if not temple or temple == "Select Temple":
        return json_error("Temple is required")

    if not festival or festival == "Select Festival":
        return json_error("Festival is required")

    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT low_limit, medium_limit, high_limit, updated_at, dataset
        FROM data_limits
        WHERE temple = ? AND festival = ?
        ORDER BY id DESC
        LIMIT 1
    """, (temple, festival))

    row = cur.fetchone()
    con.close()

    if row:
        low, medium, high, updated_at, dataset_path = row
    else:
        low, medium, high, updated_at, dataset_path = 200000, 400000, 600000, "N/A", None

    seed = sum(ord(c) for c in (temple + festival))

    morning_count = 100000 + (seed * 37) % 300000
    afternoon_count = 150000 + (seed * 53) % 350000
    evening_count = 200000 + (seed * 71) % 450000

    return jsonify({
        "temple": temple,
        "festival": festival,
        "last_updated": updated_at,
        "dataset": dataset_path,
        "Morning": {
            "count": morning_count,
            "risk": get_risk(morning_count, low, medium, high)
        },
        "Afternoon": {
            "count": afternoon_count,
            "risk": get_risk(afternoon_count, low, medium, high)
        },
        "Evening": {
            "count": evening_count,
            "risk": get_risk(evening_count, low, medium, high)
        }
    })


# ------------------ COMMENTS ------------------

@app.route("/comment", methods=["POST"])
def add_comment():
    temple = request.form.get("temple", "").strip()
    festival = request.form.get("festival", "").strip()
    email = request.form.get("email", "").strip()
    text = request.form.get("comment", "").strip()
    time_str = datetime.now().strftime("%d %b %Y %H:%M")

    if not temple or temple == "Select Temple":
        return json_error("Temple is required")

    if not festival or festival == "Select Festival":
        return json_error("Festival is required")

    if not email:
        return json_error("Email is required")

    if not text:
        return json_error("Comment is required")

    con = get_db()
    cur = con.cursor()

    cur.execute(
        "SELECT id FROM festivals WHERE temple = ? AND festival = ?",
        (temple, festival)
    )
    exists = cur.fetchone()
    if not exists:
        con.close()
        return json_error("Selected festival does not exist for temple")

    cur.execute(
        "INSERT INTO comments (temple, festival, email, comment, time) VALUES (?, ?, ?, ?, ?)",
        (temple, festival, email, text, time_str)
    )
    con.commit()
    con.close()

    return jsonify({"message": "Comment added"})


@app.route("/comments", methods=["GET"])
def get_comments():
    temple = request.args.get("temple", "").strip()
    festival = request.args.get("festival", "").strip()

    con = get_db()
    cur = con.cursor()

    if temple and festival:
        cur.execute("""
            SELECT id, temple, festival, email, comment, time
            FROM comments
            WHERE temple = ? AND festival = ?
            ORDER BY id DESC
            LIMIT 100
        """, (temple, festival))
    elif temple:
        cur.execute("""
            SELECT id, temple, festival, email, comment, time
            FROM comments
            WHERE temple = ?
            ORDER BY id DESC
            LIMIT 100
        """, (temple,))
    else:
        cur.execute("""
            SELECT id, temple, festival, email, comment, time
            FROM comments
            ORDER BY id DESC
            LIMIT 100
        """)

    rows = cur.fetchall()
    con.close()

    return jsonify([
        {
            "id": r[0],
            "temple": r[1],
            "festival": r[2],
            "email": r[3],
            "comment": r[4],
            "time": r[5]
        }
        for r in rows
    ])


@app.route("/delete-comment", methods=["DELETE"])
def delete_comment():
    comment_id = request.args.get("id", "").strip()

    if not comment_id:
        return json_error("Comment id is required")

    con = get_db()
    cur = con.cursor()
    cur.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    deleted = cur.rowcount
    con.commit()
    con.close()

    if deleted == 0:
        return json_error("Comment not found", 404)

    return jsonify({"message": "Comment deleted"})


# ------------------ RUN ------------------

if __name__ == "__main__":
    app.run(debug=True)