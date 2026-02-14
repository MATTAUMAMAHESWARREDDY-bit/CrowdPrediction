from flask import Flask, request, jsonify, send_file
import sqlite3, os
from datetime import datetime

app = Flask(__name__)

DB = "database.db"
UPLOAD_FOLDER = "datasets"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ------------------ DATABASE ------------------

def get_db():
    return sqlite3.connect(DB)

def init_db():
    con = get_db()
    cur = con.cursor()

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
        email TEXT,
        comment TEXT,
        time TEXT
    )
    """)

    con.commit()
    con.close()

init_db()

# ------------------ ROUTES ------------------

@app.route("/")
def home():
    return send_file("index.html")

# ADMIN LOGIN
@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.json
    if data["username"] == "mahi" and data["password"] == "mahi4248":
        return jsonify({"status":"success"})
    return jsonify({"status":"fail"})

# ADD FESTIVAL
@app.route("/add-festival", methods=["POST"])
def add_festival():
    temple = request.form["temple"]
    festival = request.form["festival"]

    con = get_db()
    cur = con.cursor()
    cur.execute("INSERT INTO festivals (temple, festival) VALUES (?,?)",
                (temple, festival))
    con.commit()
    con.close()

    return jsonify({"message":"Festival added"})

# ADD DATA + LIMITS (LOW + MEDIUM + HIGH)
@app.route("/add-data", methods=["POST"])
def add_data():
    temple = request.form["temple"]
    festival = request.form["festival"]
    low = int(request.form["low"])
    medium = int(request.form["medium"])
    high = int(request.form["high"])
    file = request.files["dataset"]

    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    con = get_db()
    cur = con.cursor()
    cur.execute("""
    INSERT INTO data_limits (temple, festival, low_limit, medium_limit, high_limit, dataset, updated_at)
    VALUES (?,?,?,?,?,?,?)
    """,(temple, festival, low, medium, high, path, datetime.now().strftime("%Y-%m-%d %H:%M")))
    con.commit()
    con.close()

    return jsonify({"message":"Data saved"})

# GET CROWD STATUS (DEMO LOGIC)
@app.route("/crowd")
def crowd_status():
    # Demo static numbers (later replace with ML prediction)
    morning_count = 500000
    afternoon_count = 420000
    evening_count = 990000

    def get_risk(count, low, medium, high):
        if count <= low:
            return "Low"
        elif count <= medium:
            return "Medium"
        else:
            return "High"

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT low_limit, medium_limit, high_limit, updated_at FROM data_limits ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    con.close()

    if row:
        low, medium, high, updated_at = row
    else:
        low, medium, high, updated_at = 200000, 400000, 600000, "N/A"

    return jsonify({
        "last_updated": updated_at,
        "Morning": {"count": morning_count, "risk": get_risk(morning_count, low, medium, high)},
        "Afternoon": {"count": afternoon_count, "risk": get_risk(afternoon_count, low, medium, high)},
        "Evening": {"count": evening_count, "risk": get_risk(evening_count, low, medium, high)}
    })

# ADD COMMENT
@app.route("/comment", methods=["POST"])
def comment():
    email = request.form["email"]
    text = request.form["comment"]
    time = datetime.now().strftime("%d %b %Y %H:%M")

    con = get_db()
    cur = con.cursor()
    cur.execute("INSERT INTO comments VALUES (NULL,?,?,?)",
                (email, text, time))
    con.commit()
    con.close()

    return jsonify({"message":"Comment added"})

# ------------------ RUN ------------------

if __name__ == "__main__":
    app.run(debug=True)
