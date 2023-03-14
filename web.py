import datetime
import math

from flask import Flask, render_template, request
from flask_caching import Cache
import sqlite3

app = Flask(__name__)
app.template_folder = "./templates"
app.config["TEMPLATES_AUTO_RELOAD"] = True

cache = Cache(app=app, config={'CACHE_TYPE': 'redis', 'CACHE_REDIS_URL': 'redis://redis:6379/0'})

@app.route("/")
@cache.cached(timeout=60 * 60 * 24, query_string=True) # Cache the response for 1 day
def index():
    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()

    # Get the page number from the query parameters or default to 1
    page = int(request.args.get("p", 1))

    # Calculate the offset based on the page number and the pagination size of 20
    offset = (page - 1) * 20

    # Fetch stories for the current page from the database filtering on those that were posted today and have a summary
    cursor.execute(
        "SELECT COUNT(*) FROM stories WHERE time >= ? AND summary IS NOT NULL",
        (datetime.datetime.now().timestamp() - 86400,),
    )
    total_count = cursor.fetchone()[0]

    total_pages = math.ceil(total_count / 20)

    cursor.execute(
        "SELECT * FROM stories WHERE summary IS NOT NULL ORDER BY time DESC, score DESC LIMIT 20 OFFSET ?",
        (offset,),
    )
    stories = cursor.fetchall()

    # Get the time of the most recent item in the db
    cursor.execute(
        "SELECT time FROM stories ORDER BY time DESC LIMIT 1"
    )
    latest = cursor.fetchone()[0]
    # Convert to datetime utc string
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
