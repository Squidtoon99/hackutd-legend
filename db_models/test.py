from . import db


class Test(db.Model):
    __tablename__ = "tests"

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.String(16), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    status = db.Column(db.String(32), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    evidence = db.Column(db.Text, nullable=True)
    # Detailed instruction fields moved here from Todo. Stored as JSON for
    # portability and to preserve structure (target, context, steps, etc.).
    target = db.Column(db.JSON, nullable=True)
    context = db.Column(db.JSON, nullable=True)
    prechecks = db.Column(db.JSON, nullable=True)
    steps = db.Column(db.JSON, nullable=True)
    postchecks = db.Column(db.JSON, nullable=True)
    rollback = db.Column(db.JSON, nullable=True)

    # One-to-many relationship: a Test can have multiple Todo items
    todos = db.relationship(
        "Todo", backref="test", cascade="all, delete-orphan", lazy="dynamic"
    )

    # One-to-many relationship: a Test can have multiple Stream events
    streams = db.relationship(
        "Stream", backref="test", cascade="all, delete-orphan", lazy="dynamic"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "server_id": self.server_id,
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "summary": self.summary,
            "evidence": self.evidence,
            "target": self.target,
            "context": self.context,
            "prechecks": self.prechecks,
            "steps": self.steps,
            "postchecks": self.postchecks,
            "rollback": self.rollback,
        }
