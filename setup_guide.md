# User Setup Guide: Public Release Preparation

To get your Evil AI Scraper working on GitHub Pages with your local classification model, you need to configure a few external services. Follow these steps:

## 1. Supabase & Database Setup
Supabase will handle your users, the leaderboard, and store your scraping data in the cloud.

1.  **Create a Project**: Go to [Supabase.com](https://supabase.com/), sign up, and create a "New Project".
2.  **Get API Keys**: 
    - In your Supabase dashboard, go to **Project Settings** > **API**.
    - Copy the **Project URL** and the **`anon` public API key**.
    - Open `frontend/app.js` and paste them at the top:
      ```javascript
      const SUPABASE_URL = 'https://your-project-id.supabase.co'
      const SUPABASE_KEY = 'your-anon-key'
      ```
3.  **Get Database URL**:
    - Go to **Project Settings** > **Database**.
    - Find the **Connection string** (URI). It will look like `postgresql://postgres:[YOUR-PASSWORD]@db.your-id.supabase.co:5432/postgres`.
    - Create (or update) a `.env` file in the project root with this URL:
      ```env
      DATABASE_URL=postgresql://postgres:yourpassword@db.yourproject.supabase.co:5432/postgres
      ```

## 2. Google Login Setup
This is required to identify users and track the leaderboard.

1.  **Google Cloud Console**: Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  **Create Credentials**: 
    - Create a new project.
    - Go to **APIs & Services** > **OAuth consent screen**. Set it up as "External".
    - Go to **Credentials** > **Create Credentials** > **OAuth client ID**.
    - Select **Web application**.
3.  **Callback URL**:
    - In your Supabase dashboard, go to **Authentication** > **Providers** > **Google**.
    - Copy the **Redirect URI** provided by Supabase.
    - Paste this into the **Authorized redirect URIs** section in the Google Cloud Console.
4.  **Finalize Supabase**:
    - Copy the **Client ID** and **Client Secret** from Google Cloud.
    - Paste them into the Supabase Google Auth settings and save.

## 3. Exposing your Local Backend
Since your models run on your Mac, the GitHub Pages site needs a public URL to talk to your laptop.

1.  **Install Ngrok**: (If you don't have it) `brew install ngrok`.
2.  **Start Tunnel**: Run this in your terminal:
    ```bash
    ngrok http 8001
    ```
3.  **Update Frontend**: 
    - Ngrok will give you a "Forwarding" URL (e.g., `https://random-id.ngrok-free.app`).
    - Open `frontend/app.js` again and update the `API_BASE`:
      ```javascript
      const API_BASE = 'https://your-ngrok-url.app/api'
      ```

## 4. Run the Backend
Ensure your backend is running and connected to Supabase:

1.  **Install dependencies**: `pip install -r requirements.txt` (This now includes `psycopg2-binary`).
2.  **Start Backend**: `python run.py`.

## 5. Deploy to GitHub Pages
1.  Push your repository to GitHub.
2.  Go to your repo **Settings** > **Pages**.
3.  Select the **`main`** branch and the **`/frontend`** folder (or move the frontend files to the root of a specific branch).

> [!IMPORTANT]
> **CORS Security**: I have added `CORSMiddleware` to `app.py` allowing all origins `*` for testing. Once you have your GitHub Pages URL (e.g., `https://buno.github.io`), you should update `app.py` to only allow that specific domain for better security.

> [!TIP]
> **Keep Ngrok Running**: For other people to use your site, your Mac needs to be awake, the FastAPI server must be running, and the Ngrok tunnel must be active.
