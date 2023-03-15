import datetime
import math

from flask import Flask, render_template, request
from flask_caching import Cache
import sqlite3

app = Flask(__name__)
app.template_folder = "./templates"
app.config["TEMPLATES_AUTO_RELOAD"] = True

cache = Cache(app=app, config={'CACHE_TYPE': 'redis', 'CACHE_REDIS_URL': 'redis://redis:6379/0'})

@cache.cached(timeout=60 * 60 * 24, query_string=True)
@app.route("/")
def index():
    """
    Renders the homepage with a list of 20 latest stories, paginated by 20 per page.

    Returns:
        HTML template: index.html
    """
    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()

    # Determine the current page and the offset of the stories to be retrieved
    page = int(request.args.get("p", 1))
    offset = (page - 1) * 20

    # Retrieve the total count of stories and calculate the total number of pages
    cursor.execute("SELECT COUNT(*) FROM stories WHERE summary IS NOT NULL")
    total_count = cursor.fetchone()[0]
    total_pages = math.ceil(total_count / 20)

    # Retrieve the latest 20 stories and their corresponding timestamps
    cursor.execute(
        "SELECT * FROM stories WHERE summary IS NOT NULL ORDER BY time DESC, score DESC LIMIT 20 OFFSET ?",
        (offset,),
    )
    stories = cursor.fetchall()

    # Retrieve the latest timestamp and format it in a user-friendly way
    cursor.execute("SELECT time FROM stories ORDER BY time DESC LIMIT 1")
    latest = cursor.fetchone()[0]
    latest = datetime.datetime.utcfromtimestamp(latest).strftime("%Y-%m-%d %H:%M:%S")

    conn.close()

    return render_template(
        "index.html",
        stories=stories,
        page=page,
        total_pages=total_pages,
        max=max,
        min=min,
        latest=latest,
    )