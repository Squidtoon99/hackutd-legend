from . import db


class Server(db.Model):
    __tablename__ = "servers"

    id = db.Column(db.String(16), primary_key=True)
    status = db.Column(db.String(32), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
        }
