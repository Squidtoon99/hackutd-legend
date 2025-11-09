from . import db


class Result(db.Model):
    __tablename__ = "results"
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.String(128), unique=True, nullable=False)
    status = db.Column(db.String(32), nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    evidence = db.Column(db.JSON, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "test_id": self.test_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "summary": self.summary,
            "evidence": self.evidence,
        }
