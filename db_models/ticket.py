from . import db


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.String(16), nullable=False)
    jira_id = db.Column(db.String(64), nullable=False)

    # tests = db.relationship(
    #     "Test", backref="ticket", cascade="all, delete-orphan", lazy="dynamic"
    # )

    def to_dict(self):
        return {
            "id": self.id,
            "server": self.server_id,
            "jira_id": self.jira_id,
        }
