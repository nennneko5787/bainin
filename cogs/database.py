import os

import asyncpg
import dotenv
from aiokyasher import Kyash
from aiopaypaython import PayPay

dotenv.load_dotenv()


class Database:
    pool: asyncpg.Pool = None

    @classmethod
    async def connect(cls):
        cls.pool = await asyncpg.create_pool(os.getenv("dsn"), statement_cache_size=0)
