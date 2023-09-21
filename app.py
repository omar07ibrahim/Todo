from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
import requests

app = Flask(__name__)
app.secret_key = 'lopux'
bootstrap = Bootstrap(app)
app.app_context().push()

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tasks.db'
db = SQLAlchemy(app)

def get_weather_in_baku():
    api_key = '886705b4c1182eb1c69f28eb8c520e20'
    city = 'Baku'
    url  = f"https://api.openweathermap.org/data/2.5/weather?q={city}&lang=az&units=metric&appid={api_key}"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        pogoda = data['weather'][0]['description']
        temperatura = data['main']['temp']
        return f'Погода в Баку: {pogoda.capitalize()}, Температура: {temperatura}°C'
    else:
        print(response)
        return 'Не удалось получить данные о погоде'

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, default=False)

db.create_all()

@app.route('/get_weather')
def get_weather():
    weather_info = get_weather_in_baku()
    return jsonify(weather_info)

@app.route('/')
def index():
    tasks = Task.query.all()
    return render_template('index.html', tasks=tasks)

@app.route('/add_task', methods=['POST'])
def add_task():
    task = request.form.get('task')
    if task:
        new_task = Task(task=task)
        db.session.add(new_task)
        db.session.commit()
        flash('Задача добавлена', 'success')
    else:
        flash('Введите задачу', 'danger')
    return redirect(url_for('index'))

@app.route('/delete_task/<int:id>')
def delete_task(id):
    task_to_delete = Task.query.get(id)
    if task_to_delete:
        db.session.delete(task_to_delete)
        db.session.commit()
        flash('Задача удалена', 'success')
    else:
        flash('Неверный индекс задачи', 'danger')
    return redirect(url_for('index'))

@app.route('/edit_task/<int:id>', methods=['GET', 'POST'])
def edit_task(id):
    if request.method == 'POST':
        new_task = request.form.get('new_task')
        task_to_edit = Task.query.get(id)
        if task_to_edit and new_task:
            task_to_edit.task = new_task
            db.session.commit()
            flash('Задача изменена', 'success')
            return redirect(url_for('index'))  # Redirect to the index page after editing
        else:
            flash('Неверный индекс задачи или пустое поле', 'danger')
    return render_template('edit_task.html', task_id=id)  # Render an edit_task.html template for GET requests


@app.route('/toggle_task/<int:id>')
def toggle_task(id):
    task_to_toggle = Task.query.get(id)
    if task_to_toggle:
        task_to_toggle.done = not task_to_toggle.done
        db.session.commit()
        flash('Статус задачи изменен', 'success')
    else:
        flash('Неверный индекс задачи', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
