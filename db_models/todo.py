from . import db


class Todo(db.Model):
    """Simplified Todo model.

    Storage contract: this model only keeps a reference to the owning test and a
    short name and status. All detailed instructions (target, context, steps,
    etc.) belong on the Test model.
    """

    __tablename__ = "todos"

    # internal id kept as primary key for DB operations. This allows multiple
    # Todo rows to reference the same test (one-to-many relationship).
    id = db.Column(db.Integer, primary_key=True)

    # Reference to the Test that owns the detailed instruction set
    test_id = db.Column(
        db.Integer, db.ForeignKey("tests.id"), nullable=False, index=True
    )

    # Minimal identifying fields requested by the user
    name = db.Column(db.String(128), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="pending")

    # optional: keep table args explicit (index already applied via column)
    # __table_args__ = (db.Index("ix_todos_test_id", "test_id"),)

    def to_dict(self) -> dict:
        """Return only the minimal tuple-like representation.

        As requested, the external format is (test_id, name, status).
        """
        return {"test_id": self.test_id, "name": self.name, "status": self.status}
