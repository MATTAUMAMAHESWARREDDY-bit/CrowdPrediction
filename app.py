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
        festival TEXT,
        high_limit INTEGER,
        medium_limit INTEGER,
        dataset TEXT
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

# ADMIN LOGIN (simple check)
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

# ADD DATA + LIMITS
@app.route("/add-data", methods=["POST"])
def add_data():
    festival = request.form["festival"]
    high = request.form["high"]
    medium = request.form["medium"]
    file = request.files["dataset"]

    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    con = get_db()
    cur = con.cursor()
    cur.execute("""
    INSERT INTO data_limits (festival, high_limit, medium_limit, dataset)
    VALUES (?,?,?,?)
    """,(festival, high, medium, path))
    con.commit()
    con.close()

    return jsonify({"message":"Data saved"})

# GET CROWD STATUS (STATIC LOGIC for now)
@app.route("/crowd")
def crowd_status():
    return jsonify({
        "Morning":"Medium",
        "Afternoon":"Medium",
        "Evening":"High"
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
