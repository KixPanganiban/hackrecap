# HackRecape

HackRecap is a Python project that fetches the top stories from Hacker News, fetches their text content from the original webpage, and summarizes them using OpenAI's text-davinci-03 model. The summarized stories are then displayed in a paginated list on a Flask web app.

## Requirements

Docker, or Python 3.11 and Redis if running without Docker

## Getting started

To get started, follow these steps:

1. Clone this repository:

    git clone https://github.com/kixpanganiban/hackrecap.git

2. Navigate to the project directory:

    cd hackrecap

3. Build the Docker images:

    docker compose build

4. Start the Docker containers:

    docker compose up

5. Run the summarizer:

    OPENAI_KEY=xxx docker compose exec web python summarizer.py

6. Open your web browser and go to http://localhost:8888.

## Configuration

The following environment variables need to be set to configure the app:

- `OPENAI_KEY`: Your OpenAI API key (required to use the app).

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- The Hacker News API: https://github.com/HackerNews/API
- Flask: https://flask.palletsprojects.com/en/2.1.x/
- Docker: https://www.docker.com/
- Docker Compose: https://docs.docker.com/compose/
- OpenAI API: https://beta.openai.com/docs/api/
- Redis: https://redis.io/
- SQLite: https://www.sqlite.org/index.html
- Goose: https://github.com/grangier/python-goose