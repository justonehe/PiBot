"""
PiBot Dashboard - Static Version (Server-Side Rendered)
No JavaScript, pure HTML/CSS for maximum compatibility
"""

from flask import Blueprint, render_template_string
from datetime import datetime
import json
from pathlib import Path

dashboard_bp = Blueprint("dashboard", __name__)

DASHBOARD_DATA_FILE = Path("dashboard_data.json")


def get_dashboard_data():
    """Get dashboard data from file."""
    if DASHBOARD_DATA_FILE.exists():
        try:
            with open(DASHBOARD_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass

    # Default data
    return {
        "weather": {
            "location": "Shanghai",
            "current": {
                "temp": 22,
                "condition": "sunny",
                "humidity": 65,
                "wind": "3级",
            },
            "forecast": [
                {"day": "明天", "condition": "cloudy", "high": 23, "low": 18},
                {"day": "后天", "condition": "rainy", "high": 20, "low": 16},
                {"day": "周五", "condition": "sunny", "high": 25, "low": 19},
            ],
        },
        "todos": [],
        "workers": [
            {
                "id": "worker_1",
                "name": "Worker-1",
                "status": "idle",
                "statusText": "闲置",
            },
            {
                "id": "worker_2",
                "name": "Worker-2",
                "status": "offline",
                "statusText": "离线",
            },
            {
                "id": "worker_3",
                "name": "Worker-3",
                "status": "offline",
                "statusText": "离线",
            },
        ],
    }


@dashboard_bp.route("/dashboard")
def dashboard():
    """Static dashboard with server-side rendering."""
    data = get_dashboard_data()

    # Weather icons
    weather_icons = {
        "sunny": "☀️",
        "cloudy": "☁️",
        "rainy": "🌧️",
        "snowy": "❄️",
        "stormy": "⛈️",
        "foggy": "🌫️",
    }

    weather = data.get("weather", {})
    current = weather.get("current", {})
    forecast = weather.get("forecast", [])
    todos = data.get("todos", [])
    workers = data.get("workers", [])

    # Build forecast HTML
    forecast_html = ""
    for day in forecast:
        icon = weather_icons.get(day.get("condition", ""), "🌤️")
        forecast_html += f"""
            <div class="forecast-day">
                <div class="day">{day.get("day", "")}</div>
                <div class="icon">{icon}</div>
                <div class="temp">{day.get("high", "--")}° / {day.get("low", "--")}°</div>
            </div>
        """

    # Build todos HTML
    todos_html = ""
    if not todos:
        todos_html = '<li class="loading">暂无待办事项</li>'
    else:
        for todo in todos:
            done_class = "done" if todo.get("done") else ""
            checked = "checked" if todo.get("done") else ""
            todos_html += f"""
                <li class="todo-item">
                    <input type="checkbox" class="todo-checkbox" {checked} disabled>
                    <span class="todo-text {done_class}">{todo.get("text", "")}</span>
                </li>
            """

    # Build workers HTML
    workers_html = ""
    for worker in workers:
        status = worker.get("status", "offline")
        if status == "active":
            icon = "🔥"
        elif status == "idle":
            icon = "💤"
        else:
            icon = "❌"

        workers_html += f"""
            <div class="worker-card {status}">
                <div class="worker-icon">{icon}</div>
                <div class="worker-name">{worker.get("name", "")}</div>
                <div class="worker-status">{worker.get("statusText", "")}</div>
            </div>
        """

    # Current datetime
    now = datetime.now()
    datetime_str = now.strftime("%Y年%m月%d日 %A %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="30">
    <title>PiBot Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 20px;
        }}
        .dashboard {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            grid-template-rows: auto auto 1fr;
            gap: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            grid-column: 1 / -1;
            text-align: center;
            color: white;
            padding: 20px;
        }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .datetime {{ font-size: 1.2em; opacity: 0.9; }}
        .section-title {{
            font-size: 1.3em;
            font-weight: bold;
            margin-bottom: 15px;
            color: #667eea;
        }}
        .weather-current {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        .weather-icon {{ font-size: 4em; }}
        .weather-info h2 {{ font-size: 3em; margin-bottom: 5px; }}
        .weather-info p {{ color: #666; font-size: 1.1em; }}
        .forecast-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 15px;
        }}
        .forecast-day {{
            text-align: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 12px;
        }}
        .forecast-day .day {{ font-weight: bold; color: #667eea; }}
        .forecast-day .icon {{ font-size: 2em; margin: 10px 0; }}
        .todo-list {{ list-style: none; }}
        .todo-item {{
            display: flex;
            align-items: center;
            padding: 12px;
            margin-bottom: 8px;
            background: #f8f9fa;
            border-radius: 10px;
        }}
        .todo-checkbox {{ width: 20px; height: 20px; margin-right: 12px; }}
        .todo-text.done {{ text-decoration: line-through; color: #999; }}
        .workers-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
        }}
        .worker-card {{
            text-align: center;
            padding: 20px;
            border-radius: 12px;
            background: #f8f9fa;
        }}
        .worker-card.active {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
        }}
        .worker-card.idle {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        .worker-icon {{ font-size: 2.5em; margin-bottom: 10px; }}
        .loading {{ text-align: center; color: #999; padding: 20px; }}
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>🤖 PiBot Dashboard</h1>
            <div class="datetime">{datetime_str}</div>
        </div>

        <div class="card">
            <div class="section-title">🌤️ 天气 - {weather.get("location", "Unknown")}</div>
            <div class="weather-current">
                <div class="weather-icon">{weather_icons.get(current.get("condition"), "🌤️")}</div>
                <div class="weather-info">
                    <h2>{current.get("temp", "--")}°C</h2>
                    <p>湿度 {current.get("humidity", "--")}% | {current.get("wind", "")}</p>
                </div>
            </div>
            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee;">
                <div class="section-title" style="font-size: 1em;">📅 未来3天</div>
                <div class="forecast-grid">
                    {forecast_html}
                </div>
            </div>
        </div>

        <div class="card">
            <div class="section-title">📝 待办事项 ({len(todos)})</div>
            <ul class="todo-list">
                {todos_html}
            </ul>
        </div>

        <div class="card" style="grid-column: 1 / -1;">
            <div class="section-title">👷 Worker 状态</div>
            <div class="workers-grid">
                {workers_html}
            </div>
        </div>
    </div>
</body>
</html>"""

    return html


@dashboard_bp.route("/api/dashboard/data")
def dashboard_data():
    """API endpoint for dashboard data."""
    return get_dashboard_data()
