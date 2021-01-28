import asyncpg


class DatabaseClient:
    def __init__(self, user, password, database, host):
        self.user = user
        self.password = password
        self.database = database
        self.host = host
        self.conn = None

    async def connect(self):
        try:
            login_data = {"user": self.user, "password": self.password, "database": self.database, "host": self.host}
            self.conn = await asyncpg.create_pool(**login_data)
        except Exception as ex:
            # TODO: Add logging function here
            raise ex

    def get_pool(self):
        return self.conn
