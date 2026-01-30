# Reddit Keyword Monitor

This project is an automated Python bot that monitors specific subreddits for new posts containing defined keywords. When a post matches the criteria, the bot uses AI (Google Gemini) to analyze it, and if it deems it relevant, it sends a notification to a Discord server.

## Features

- **Subreddit Monitoring**: The bot periodically checks for new posts in a list of subreddits defined in `config.json`.
- **Keyword Detection**: It scans the title and content of each new post for keywords from `config.json`.
- **AI Analysis**: It uses the Google Gemini language model to assess whether a found post describes a real technical issue rather than just a complaint.
- **Discord Notifications**: It sends an alert to a defined Discord webhook, including the post's title, a link to the post, and the keyword found.
- **Post History**: It saves links to processed posts in `historia_postow.txt` to avoid duplicate analyses and notifications.
- **Error Handling and Logging**: It maintains a detailed event log in `monitor.log` and handles basic network errors and API limits.

## How It Works

1.  **Configuration**: The bot loads the list of subreddits, keywords, and other settings from the `config.json` file.
2.  **Post Retrieval**: At a specified interval (`sleep_time`), the bot connects to the subreddits' RSS feeds to fetch new posts.
3.  **Filtering**: Each post is checked for the presence of keywords. Posts that have already been processed (are in `historia_postow.txt`) are ignored.
4.  **Analysis Queue**: Posts containing keywords are placed in a queue.
5.  **AI Analysis**: The bot processes the queue by sending the content of each post to the Gemini AI model for evaluation (`"YES"` or `"NO"`). An `ai_delay` is used between analyses to avoid exceeding API limits.
6.  **Sending an Alert**: If the AI responds with `"YES"`, the bot generates and sends a notification to Discord.

## Installation and Setup

### Prerequisites

- Python 3.x
- Git

### Steps

1.  **Clone the repository:**
    ```bash
    git clone <https://github.com/jbialascreateit-gif/reddit-monitor.git>
    cd <reddit-monitor>
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure environment variables:**

    Create a file named `.env` in the main project folder. It will store your API keys. Add the following entries to it:

    ```
    GEMINI_API_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE"
    DISCORD_WEBHOOK_URL="PASTE_YOUR_DISCORD_WEBHOOK_URL_HERE"
    ```

    - **To get a Gemini API key**: Visit [Google AI Studio](https://aistudio.google.com/app/apikey).
    - **To get a Discord webhook URL**: In your Discord server settings, go to `Integrations > Webhooks > New Webhook`.

4.  **Customize the configuration:**

    Open the `config.json` file and adjust it to your needs:
    - `subreddits`: A list of subreddits to monitor (without the `r/` prefix).
    - `keywords`: A list of keywords the bot should react to.
    - `sleep_time`: The time in seconds between each cycle of checking subreddits.
    - `ai_delay`: The time in seconds between AI queries to avoid rate limits.

5.  **Run the script:**
    ```bash
    python monitor.py
    ```

    The bot will start running and will display logs in the console and save them to the `monitor.log` file.

## File Structure

-   `monitor.py`: The main application script.
-   `config.json`: The configuration file (subreddits, keywords, delays).
-   `requirements.txt`: The list of Python dependencies.
-   `.env`: (To be created by you) Stores API keys.
-   `historia_postow.txt`: An automatically generated file that stores the history of checked posts.
-   `monitor.log`: An automatically generated file containing the bot's logs.
-   `.gitignore`: Defines which files should be ignored by Git (e.g., `.env`, `__pycache__`).