import datetime
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import os
import requests

from goose3 import Goose
import redis
import openai
import tiktoken


def initialize_database():
    """Initialize database and create necessary tables."""
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
    """Fetches today's stories from HackerNews API returns them as a list of dicts."""

    def get_story_details(story_id):
        url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        response = requests.get(url)
        return response.json()

    url = "https://hacker-news.firebaseio.com/v0/topstories.json"
    response = requests.get(url)
    print(f"Retrieved {len(response.json())} stories.")

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
                print(f"Skipped story: {story_details['id']}")
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
                print(f"Added story: {story_details['title']}")

            # Close the connection and cursor for each thread
            cursor_thread.close()
            conn_thread.close()

    print("Done fetching stories.")


def fetch_article_texts():
    def _fetch_text_job(story):
        try:
            g = Goose({"enable_image_fetching": True})
            article = g.extract(url=story[2])
        except:
            print(f"Failed to fetch article text for story: {story[1]}")
        else:
            conn = sqlite3.connect("db.sqlite")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE stories SET text = ?, image = ? WHERE id = ?",
                (
                    article.cleaned_text,
                    article.top_image.src if article.top_image else "",
                    story[0],
                ),
            )
            conn.commit()
            print(f"Added text to story: {story[1]}")
            conn.close()

    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stories WHERE text IS NULL")
    stories = cursor.fetchall()
    conn.close()
    print(f"Fetching article texts for {len(stories)} stories.")
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(_fetch_text_job, story) for story in stories]
        for future in futures:
            future.result()

    print("Done fetching article texts.")


def count_tokens(text):
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return len(encoding.encode(text))


def chunk_text(text, max_tokens):
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    tokens = encoding.encode(text)
    chunks = []

    current_chunk = []
    current_token_count = 0

    for token in tokens:
        if current_token_count + 1 <= max_tokens:
            current_chunk.append(token)
            current_token_count += 1
        else:
            chunks.append(encoding.decode(current_chunk))
            current_chunk = [token]
            current_token_count = 1

    if current_chunk:
        chunks.append(encoding.decode(current_chunk))

    return chunks


def summarize_text(text):
    openai.api_key = os.environ["OPENAI_KEY"]
    model_engine = "text-davinci-003"
    prompt_template = "{}\n\nTl;dr (max 200 words)"
    max_tokens = 500  # set the size of each chunk

    def recursive_summarize(text):
        chunks = chunk_text(text, max_tokens)
        summaries = []

        # Summarize each chunk separately using the OpenAI API
        for chunk in chunks:
            prompt = prompt_template.format(chunk)

            response = openai.Completion.create(
                engine=model_engine,
                prompt=prompt,
                max_tokens=150,
                n=1,
                stop=None,
                temperature=0.5,
            )

            summary = response.choices[0].text.strip()
            summaries.append(summary)

        combined_summary = " ".join(summaries)

        if count_tokens(combined_summary) > 4000:
            return recursive_summarize(combined_summary)
        else:
            return combined_summary

    final_summary = recursive_summarize(text)

    cohesion_prompt = f"{final_summary}\n\nTl;dr (max 2 paragraphs)"

    response = openai.Completion.create(
        engine=model_engine,
        prompt=cohesion_prompt,
        temperature=0.7,
        max_tokens=300,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1,
    )

    rewritten_summary = response.choices[0].text.strip()

    return rewritten_summary


# Fetch all texts from the database and summarize them
def summarize_all_texts():
    def _summarize_job(story):
        if not story[4]:
            return
        try:
            summary = summarize_text(story[4])
        except Exception as e:
            print(f"Failed to summarize text for story: {story[1]}. Error: {str(e)}")
        else:
            conn = sqlite3.connect("db.sqlite")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE stories SET summary = ? WHERE id = ?", (summary, story[0])
            )
            conn.commit()
            print(f"Added summary to story: {story[1]}")
            conn.close()

    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stories WHERE summary IS NULL AND text IS NOT NULL")
    stories = cursor.fetchall()
    conn.close()

    print(f"Summarizing texts for {len(stories)} stories.")
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(_summarize_job, story) for story in stories]
        for future in futures:
            future.result()

    print("Done summarizing texts.")


if __name__ == "__main__":
    initialize_database()
    fetch_stories()
    fetch_article_texts()
    summarize_all_texts()

    # Flush redis db
    redis_client = redis.Redis(host="redis", port=6379, db=0)
    redis_client.flushdb()
