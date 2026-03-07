import pymysql
from dbutils.pooled_db import PooledDB


class Db:
    _pool = None

    @classmethod
    def init(cls, host, user, password, database, maxconnections=10):
        cls._pool = PooledDB(
            creator=pymysql,
            maxconnections=maxconnections,
            mincached=2,
            maxcached=5,
            blocking=True,
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
            host=host,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4"
        )

    @classmethod
    def get_connection(cls):
        if not cls._pool:
            raise Exception("Не получилось синициализировать пул соединений")
        return cls._pool.connection()