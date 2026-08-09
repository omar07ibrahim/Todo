"""Legacy task application with an explicit environment-only secret boundary."""

from __future__ import annotations

import os
from typing import Any

import requests
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy


def _required_signing_secret() -> str:
    value = os.environ.get("TODO_SECRET_KEY")
    if value is None or len(value) < 32 or any(character.isspace() for character in value):
        raise RuntimeError(
            "TODO_SECRET_KEY must contain at least 32 non-whitespace characters"
        )
    return value


app = Flask(__name__)
app.secret_key = _required_signing_secret()
app.config.update(
    SQLALCHEMY_DATABASE_URI=os.environ.get(
        "TODO_DATABASE_URL", "sqlite:///tasks.db"
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("TODO_COOKIE_SECURE") == "1",
)
Bootstrap(app)
db = SQLAlchemy(app)


def get_weather_in_baku() -> str:
    """Fetch optional weather data without embedding or logging credentials."""
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key:
        return "Weather integration is disabled until OPENWEATHER_API_KEY is set."

    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "appid": api_key,
                "lang": "az",
                "q": "Baku",
                "units": "metric",
            },
            timeout=(2, 5),
        )
        response.raise_for_status()
        data: Any = response.json()
        description = data["weather"][0]["description"]
        temperature = data["main"]["temp"]
    except (KeyError, IndexError, TypeError, ValueError, requests.RequestException):
        return "Weather data is temporarily unavailable."

    return (
        f"Weather in Baku: {str(description).capitalize()}, "
        f"temperature: {temperature}°C"
    )


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, default=False)


with app.app_context():
    db.create_all()


@app.get("/get_weather")
def get_weather():
    return jsonify(get_weather_in_baku())


@app.get("/")
def index():
    return render_template("index.html", tasks=Task.query.all())


@app.post("/add_task")
def add_task():
    task = request.form.get("task", "").strip()
    if task:
        db.session.add(Task(task=task[:200]))
        db.session.commit()
        flash("Task added", "success")
    else:
        flash("Enter a task", "danger")
    return redirect(url_for("index"))


@app.route("/edit_task/<int:task_id>", methods=["GET", "POST"])
def edit_task(task_id: int):
    task_to_edit = db.session.get(Task, task_id)
    if request.method == "POST":
        new_task = request.form.get("new_task", "").strip()
        if task_to_edit and new_task:
            task_to_edit.task = new_task[:200]
            db.session.commit()
            flash("Task updated", "success")
            return redirect(url_for("index"))
        flash("Unknown task or empty value", "danger")
    return render_template("edit_task.html", task_id=task_id)


@app.post("/toggle_task/<int:task_id>")
def toggle_task(task_id: int):
    task_to_toggle = db.session.get(Task, task_id)
    if task_to_toggle:
        task_to_toggle.done = not task_to_toggle.done
        db.session.commit()
        flash("Task status updated", "success")
    else:
        flash("Unknown task", "danger")
    return redirect(url_for("index"))


@app.post("/delete_task/<int:task_id>")
def delete_task(task_id: int):
    task_to_delete = db.session.get(Task, task_id)
    if task_to_delete:
        db.session.delete(task_to_delete)
        db.session.commit()
        flash("Task deleted", "success")
    else:
        flash("Unknown task", "danger")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=False)
