import datetime
from concurrent.futures import ThreadPoolExecutor
import logging
import sqlite3
import os
import requests

from bs4 import BeautifulSoup
from goose3 import Goose
from openai_summarize import OpenAISummarize
import redis


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)


def initialize_database():
    """
    Initializes the database and creates the necessary tables if they do not exist.

    Returns:
        None
    """
    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS stories
           (id INTEGER PRIMARY KEY,
           title TEXT,
           url TEXT,
           time INTEGER,
           text TEXT,
           summary TEXT,
           image TEXT,
           score INTEGER)
        """
    )
    conn.commit()
    conn.close()


def fetch_stories():
    """
    Fetches today's top stories from HackerNews API and saves them to the database.

    Returns:
        None
    """

    def get_story_details(story_id):
        """
        Retrieves details of a single story from the HackerNews API.

        Args:
            story_id (int): The ID of the story to retrieve.

        Returns:
            dict: A dictionary containing the details of the story.
        """
        url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        response = requests.get(url)
        return response.json()

    url = "https://hacker-news.firebaseio.com/v0/topstories.json"
    response = requests.get(url)
    logger.info(f"Retrieved {len(response.json())} stories.")

    with ThreadPoolExecutor() as executor:
        futures = []
        for story_id in response.json():
            # Create a new connection and cursor for each thread
            conn_thread = sqlite3.connect("db.sqlite")
            cursor_thread = conn_thread.cursor()

            # Submit the job to the executor
            future = executor.submit(get_story_details, story_id)
            futures.append((future, conn_thread, cursor_thread))

        for future, conn_thread, cursor_thread in futures:
            story_details = future.result()
            cursor_thread.execute(
                "SELECT * FROM stories WHERE id = ?", (story_details["id"],)
            )
            if cursor_thread.fetchone() is not None:
                logger.info(f"Skipped story: {story_details['id']}")
                continue
            if (
                story_details["time"] >= (datetime.datetime.now().timestamp() - 86400)
                and story_details["type"] == "story"
                and "url" in story_details
                and "title" in story_details
            ):
                cursor_thread.execute(
                    "INSERT INTO stories(id, title, url, time, score) VALUES (?, ?, ?, ?, ?)",
                    (
                        story_details["id"],
                        story_details["title"],
                        story_details["url"],
                        story_details["time"],
                        story_details["score"],
                    ),
                )
                conn_thread.commit()
                logger.info(f"Added story: {story_details['title']}")

            # Close the connection and cursor for each thread
            cursor_thread.close()
            conn_thread.close()

    logger.info("Done fetching stories.")


def fetch_article_texts():
    """Fetch and save the full article text for each story in the database."""

    def extract_tweet_text(tweet_url):
        """
        Extract tweet text using BeautifulSoup.

        Args:
            tweet_url (str): The URL of the tweet.

        Returns:
            str: The extracted tweet text, or None if extraction fails.
        """
        response = requests.get(tweet_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            tweet_text = soup.find('div', {'class': 'css-901oao r-hkyrab r-1qd0xha r-a023e6 r-16dba41 r-ad9z0x r-bcqeeo r-bnwqim r-qvutc0'})
            return tweet_text.get_text() if tweet_text else None
        else:
            return None

    def save_text_to_db(story_id, text, image=""):
        """
        Save the extracted text and image to the database.

        Args:
            story_id (int): The story ID.
            text (str): The extracted text.
            image (str, optional): The image URL. Defaults to an empty string.

        Returns:
            None
        """
        conn = sqlite3.connect("db.sqlite")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE stories SET text = ?, image = ? WHERE id = ?",
            (text, image, story_id),
        )
        conn.commit()
        conn.close()

    def _fetch_text_job(story):
        """
        Extract and save the full article text for a single story.

        Args:
            story (tuple): A tuple containing the details of the story.

        Returns:
            None
        """
        url = story[2]
        if url.startswith('https://twitter.com'):
            text = extract_tweet_text(url)
            if text:
                save_text_to_db(story[0], text)
                logger.info(f"Added text to story: {story[1]}")
            else:
                logger.info(f"Failed to fetch tweet text for story: {story[1]}")
        else:
            try:
                g = Goose({"enable_image_fetching": True})
                article = g.extract(url=url)
                save_text_to_db(
                    story[0], article.cleaned_text,
                    article.top_image.src if article.top_image else ""
                )
                logger.info(f"Added text to story: {story[1]}")
            except:
                logger.info(f"Failed to fetch article text for story: {story[1]}")

    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stories WHERE text IS NULL")
    stories = cursor.fetchall()
    conn.close()
    logger.info(f"Fetching article texts for {len(stories)} stories.")
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(_fetch_text_job, story) for story in stories]
        for future in futures:
            future.result()

    logger.info("Done fetching article texts.")


def summarize_all_texts():
    """
    Summarizes the text of all stories that have not yet been summarized.

    Returns:
        None
    """

    def _summarize_job(story):
        """
        Summarizes the text of a given story and updates the summary in the database.

        Args:
            story (tuple): A tuple representing a story record in the database.

        Returns:
            None
        """
        if not story[4]:
            return
        try:
            summarizer = OpenAISummarize(openai_key=os.environ["OPENAI_KEY"])
            summary = summarizer.summarize_text(story[4])
        except Exception as e:
            logger.info(
                f"Failed to summarize text for story: {story[1]}. Error: {str(e)}"
            )
        else:
            conn = sqlite3.connect("db.sqlite")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE stories SET summary = ? WHERE id = ?", (summary, story[0])
            )
            conn.commit()
            logger.info(f"Added summary to story: {story[1]}")
            conn.close()

    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stories WHERE summary IS NULL AND text IS NOT NULL")
    stories = cursor.fetchall()
    conn.close()

    logger.info(f"Summarizing texts for {len(stories)} stories.")
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(_summarize_job, story) for story in stories]
        for future in futures:
            future.result()

    logger.info("Done summarizing texts.")


if __name__ == "__main__":
    initialize_database()
    fetch_stories()
    fetch_article_texts()
    summarize_all_texts()

    # Flush redis db
    redis_client = redis.Redis(host="redis", port=6379, db=0)
    redis_client.flushdb()
