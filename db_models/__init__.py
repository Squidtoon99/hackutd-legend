from flask_sqlalchemy import SQLAlchemy

# single shared SQLAlchemy object for the project
db = SQLAlchemy()

# import models so they are registered with SQLAlchemy when db_models is imported
from .server import Server
from .stream import Stream
from .test import Test
from .ticket import Ticket
from .todo import Todo
from .result import Result

__all__ = ["db", "Server", "Stream", "Test", "Ticket", "Todo", "Result"]
