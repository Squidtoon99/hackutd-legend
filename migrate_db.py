#!/usr/bin/env python3
"""
Database migration script for HackUTD Legend schema updates.

This script handles the migration from the old schema to the new integrated schema:
1. Adds new columns to Test table (target, context, prechecks, steps, postchecks, rollback)
2. Updates Stream table to use integer FK instead of UUID
3. Updates Todo table to simplified format (test_id, name, status)
4. Adds Result table if not exists
5. Adds relationships

IMPORTANT: Backup your database before running this!

Usage:
    python migrate_db.py
"""

import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from sqlalchemy import inspect, text

# Load environment
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Create minimal Flask app for migration
app = Flask(__name__)
db_url = os.environ.get("DEV_POSTGRES_URI")
if not db_url:
    print("❌ DEV_POSTGRES_URI environment variable not set!")
    print("   Set it to your Neon/Postgres connection string.")
    sys.exit(1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

from db_models import db, Server, Stream, Test, Ticket, Todo, Result

db.init_app(app)


def check_column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def check_table_exists(table_name: str) -> bool:
    """Check if a table exists."""
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()


def migrate_test_table():
    """Add new JSON columns to Test table."""
    print("\n📝 Migrating Test table...")

    new_columns = {
        "target": "JSON",
        "context": "JSON",
        "prechecks": "JSON",
        "steps": "JSON",
        "postchecks": "JSON",
        "rollback": "JSON",
    }

    for col_name, col_type in new_columns.items():
        if not check_column_exists("tests", col_name):
            print(f"   Adding column: {col_name} ({col_type})")
            with db.engine.connect() as conn:
                conn.execute(
                    text(f"ALTER TABLE tests ADD COLUMN {col_name} {col_type}")
                )
                conn.commit()
        else:
            print(f"   ✓ Column {col_name} already exists")

    print("✅ Test table migration complete")


def migrate_stream_table():
    """Update Stream table to use integer FK."""
    print("\n📝 Migrating Stream table...")

    # Check if old UUID column exists
    has_uuid_fk = check_column_exists("streams", "test_id_fk")
    has_int_test_id = check_column_exists("streams", "test_id")

    if has_uuid_fk:
        print("   ⚠️  Old UUID column (test_id_fk) detected")
        print("   Dropping old column and recreating with integer FK...")

        with db.engine.connect() as conn:
            # Drop old FK constraint and column
            conn.execute(
                text("ALTER TABLE streams DROP COLUMN IF EXISTS test_id_fk CASCADE")
            )

            # Ensure test_id is integer and has FK constraint
            if has_int_test_id:
                # Check if it's already integer type with FK
                inspector = inspect(db.engine)
                cols = {col["name"]: col for col in inspector.get_columns("streams")}
                test_id_col = cols.get("test_id")

                if test_id_col and "String" in str(test_id_col["type"]):
                    print("   Converting test_id from String to Integer...")
                    # Need to recreate column
                    conn.execute(text("ALTER TABLE streams DROP COLUMN test_id"))
                    conn.execute(
                        text(
                            """
                        ALTER TABLE streams 
                        ADD COLUMN test_id INTEGER NOT NULL 
                        REFERENCES tests(id) ON DELETE CASCADE
                    """
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_streams_test_id ON streams(test_id)"
                        )
                    )
            else:
                # Add test_id column
                conn.execute(
                    text(
                        """
                    ALTER TABLE streams 
                    ADD COLUMN test_id INTEGER NOT NULL 
                    REFERENCES tests(id) ON DELETE CASCADE
                """
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_streams_test_id ON streams(test_id)"
                    )
                )

            conn.commit()
    else:
        print("   ✓ Stream table already using integer FK")

    print("✅ Stream table migration complete")


def migrate_todo_table():
    """Update Todo table to simplified format."""
    print("\n📝 Migrating Todo table...")

    # Check if old columns exist
    old_columns = [
        "job_id",
        "target",
        "context",
        "prechecks",
        "steps",
        "postchecks",
        "rollback",
        "created_at",
        "updated_at",
    ]

    has_old_schema = any(check_column_exists("todos", col) for col in old_columns)
    has_test_id = check_column_exists("todos", "test_id")
    has_name = check_column_exists("todos", "name")

    if has_old_schema:
        print("   ⚠️  Old Todo schema detected")
        print("   Note: Data migration required for old todos!")
        print(
            "   Old todos will be preserved but you'll need to manually link them to tests"
        )

        # Add new columns if they don't exist
        with db.engine.connect() as conn:
            if not has_test_id:
                print("   Adding test_id column...")
                # Add as nullable first, then we can update
                conn.execute(
                    text(
                        "ALTER TABLE todos ADD COLUMN test_id INTEGER REFERENCES tests(id)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_todos_test_id ON todos(test_id)"
                    )
                )

            if not has_name:
                print("   Adding name column...")
                conn.execute(text("ALTER TABLE todos ADD COLUMN name VARCHAR(128)"))
                # Populate name from job_id if it exists
                if check_column_exists("todos", "job_id"):
                    conn.execute(
                        text("UPDATE todos SET name = job_id WHERE name IS NULL")
                    )

            # Make status column if it doesn't exist
            if not check_column_exists("todos", "status"):
                print("   Adding status column...")
                conn.execute(
                    text(
                        "ALTER TABLE todos ADD COLUMN status VARCHAR(32) DEFAULT 'pending'"
                    )
                )

            conn.commit()

        print("   ⚠️  Old columns (job_id, target, etc.) preserved for manual migration")
        print("   You can drop them after migrating data to Test records")
    else:
        if not has_test_id:
            print("   Adding test_id column...")
            with db.engine.connect() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE todos ADD COLUMN test_id INTEGER NOT NULL REFERENCES tests(id)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_todos_test_id ON todos(test_id)"
                    )
                )
                conn.commit()

        if not has_name:
            print("   Adding name column...")
            with db.engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE todos ADD COLUMN name VARCHAR(128) NOT NULL")
                )
                conn.commit()

        print("   ✓ Todo table already using new schema")

    print("✅ Todo table migration complete")


def create_result_table():
    """Create Result table if it doesn't exist."""
    print("\n📝 Creating Result table if needed...")

    if not check_table_exists("results"):
        print("   Creating results table...")
        db.create_all()
        print("   ✓ Results table created")
    else:
        print("   ✓ Results table already exists")

    print("✅ Result table check complete")


def main():
    """Run all migrations."""
    print("=" * 70)
    print("HackUTD Legend - Database Migration")
    print("=" * 70)
    print(f"Database: {db_url[:50]}...")
    print()

    response = input("⚠️  Have you backed up your database? (yes/no): ")
    if response.lower() not in ["yes", "y"]:
        print("❌ Please backup your database first!")
        print("   For Postgres: pg_dump dbname > backup.sql")
        return 1

    print("\n🚀 Starting migration...\n")

    with app.app_context():
        try:
            # Run migrations
            migrate_test_table()
            migrate_stream_table()
            migrate_todo_table()
            create_result_table()

            print("\n" + "=" * 70)
            print("✅ Migration completed successfully!")
            print("=" * 70)
            print("\n📋 Next steps:")
            print(
                "   1. If you have old Todo records, migrate their data to Test records"
            )
            print("   2. Update todo.test_id to link todos to their tests")
            print("   3. After migration, drop old columns from todos table:")
            print("      ALTER TABLE todos DROP COLUMN job_id, target, context, etc.")
            print("   4. Test your application to ensure everything works")
            print()

            return 0

        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            print("\n⚠️  Your database may be in an inconsistent state!")
            print("   Restore from backup and check the error above.")
            import traceback

            traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(main())
