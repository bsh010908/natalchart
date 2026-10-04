from sqlalchemy import text

from db.database import get_engine


with get_engine().connect() as connection:
    result = connection.execute(text("SELECT DATABASE()"))
    print(result.scalar())