from flask import Flask, render_template_string
import json
from pathlib import Path
from datetime import datetime, timedelta

app = Flask(__name__)
USERS_PATH = Path("users_data.json")
LOG_PATH = Path("quiz_activity_log.json")

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Cyber Quiz Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 2rem; background: #f9f9f9; color: #333; }
        h1 { color: #444; }
        .stats { margin-top: 1rem; }
        .stats div { margin: 0.5rem 0; }
        .panel { background: white; border-radius: 8px; padding: 1rem 2rem; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
    <div class="panel">
        <h1>📊 Cyber Quiz Stats</h1>
        <div class="stats">
            <div>Total Users: <b>{{ total_users }}</b></div>
            <div>Total Answers: <b>{{ total_logs }}</b></div>
            <div>Quizzes Today: <b>{{ today_logs }}</b></div>
            <div>Quizzes This Week: <b>{{ week_logs }}</b></div>
            <div>Quizzes This Month: <b>{{ month_logs }}</b></div>
        </div>
    </div>
</body>
</html>
'''

@app.route("/")
def dashboard():
    now = datetime.utcnow()
    today = now.date()
    start_week = today - timedelta(days=today.weekday())
    start_month = today.replace(day=1)

    users = json.load(open(USERS_PATH)) if USERS_PATH.exists() else {}
    logs = json.load(open(LOG_PATH)) if LOG_PATH.exists() else []

    today_logs = sum(1 for log in logs if datetime.fromisoformat(log["timestamp"]).date() == today)
    week_logs = sum(1 for log in logs if datetime.fromisoformat(log["timestamp"]).date() >= start_week)
    month_logs = sum(1 for log in logs if datetime.fromisoformat(log["timestamp"]).date() >= start_month)

    return render_template_string(HTML,
                                  total_users=len(users),
                                  total_logs=len(logs),
                                  today_logs=today_logs,
                                  week_logs=week_logs,
                                  month_logs=month_logs)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
