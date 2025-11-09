from sqlalchemy import Identity, func, Index
from . import db


# --- models ---
class Stream(db.Model):
    """
    Event stream (SSE) lines for a Test. Append-only.
    Each row is a single message with optional JSON meta.
    """

    __tablename__ = "streams"

    id = db.Column(
        db.BigInteger, Identity(always=True), primary_key=True, autoincrement=True
    )

    # Foreign key to Test.id (integer)
    test_id = db.Column(
        db.Integer,
        db.ForeignKey("tests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    timestamp = db.Column(
        db.DateTime(timezone=True), nullable=False, default=func.now()
    )
    message = db.Column(db.Text, nullable=False)  # human text line
    meta = db.Column(db.JSON, nullable=True)  # machine payload for UI

    __table_args__ = (Index("ix_streams_test_time", "test_id", "timestamp"),)

    def to_dict(self):
        return {
            "id": self.id,
            "test_id": self.test_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "message": self.message,
            "meta": self.meta,
        }
