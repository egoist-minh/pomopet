from pathlib import Path

from sqlalchemy import create_engine, inspect, text


database_path = Path(__file__).resolve().parents[2] / "pomopet.db"
engine = create_engine(f"sqlite:///{database_path}")

with engine.begin() as connection:
    columns = {column["name"] for column in inspect(connection).get_columns("tasks")}
    if "estimated_duration" not in columns:
        connection.execute(text("ALTER TABLE tasks ADD COLUMN estimated_duration INTEGER"))
        print("Added estimated_duration column to tasks table.")
    else:
        print("estimated_duration column already exists; nothing to do.")
