import asyncio
import hashlib
import json
from functools import wraps

import aiomysql
import structlog
from redis.asyncio import Redis
from tenacity import retry, stop_after_attempt, wait_fixed


def ensure_initialized(method):
    @wraps(method)
    async def wrapper(self, *args, **kwargs):
        if not await self.is_initialized():
            await self._initialize()
        return await method(self, *args, **kwargs)

    return wrapper


class RedisCache:
    def __init__(self, redis_config):
        self.redis_config = redis_config
        self.redis = None
        self.log = structlog.stdlib.get_logger().bind(name="redis_cache")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
    async def initialize(self):
        try:
            self.redis = Redis(**self.redis_config, socket_timeout=5, retry_on_timeout=True)
            await self.redis.ping()
            self.log.info("Redis connection is healthy")
        except Exception as e:
            self.log.error("Failed to connect to Redis", error=str(e))
            self.redis = None
            raise

    async def get(self, key):
        if self.redis is not None:
            try:
                return await self.redis.get(key)
            except Exception as e:
                self.log.warning("Redis unavailable, continuing without cache", error=str(e))
                return None
        return None

    async def set(self, key, value, expire):
        if self.redis is not None:
            try:
                await self.redis.set(key, value, ex=expire)
                self.log.info("Value cached in Redis", key=key)
            except Exception as e:
                self.log.warning("Failed to cache value in Redis", error=str(e))

    async def is_healthy(self):
        if self.redis is not None:
            try:
                await self.redis.ping()
                return True
            except Exception as e:
                self.log.error("Redis is not initialized properly", error=str(e))
        return False

    async def close(self):
        if self.redis:
            await self.redis.close()


class ChatSessionRepository:
    def __init__(self, db_config):
        self.db_config = db_config
        self.pool = None
        self.log = structlog.stdlib.get_logger().bind(name="chat_session_repository")
        self._pool_lock = asyncio.Lock()  # Lock to handle concurrent access to pool initialization

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
    async def initialize(self):
        async with self._pool_lock:
            if self.pool is None:
                try:
                    self.pool = await aiomysql.create_pool(**self.db_config, maxsize=10, minsize=1)
                    self.log.info("MySQL pool created successfully")
                except Exception as e:
                    self.log.error("Failed to create MySQL pool", error=str(e))
                    raise

    async def create_database_if_not_exists(self):
        async with aiomysql.connect(**self.db_config) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SHOW DATABASES LIKE %s", (self.db_config["db"],))
                if not await cursor.fetchone():
                    await cursor.execute(f"CREATE DATABASE {self.db_config['db']}")
        self.log.info("Database checked/created successfully")

    async def create_tables(self, num_partitions):
        await self.ensure_pool_initialized()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                for i in range(num_partitions):
                    table_name = f"chat_sessions_{i}"
                    await cursor.execute(f"""
                            CREATE TABLE IF NOT EXISTS {table_name} (
                                user_id VARCHAR(255) PRIMARY KEY, 
                                chatgpt JSON
                            )""")
                    self.log.info(f"Table '{table_name}' created successfully")
                await conn.commit()

    async def ensure_pool_initialized(self):
        async with self._pool_lock:
            if self.pool is None:
                await self.initialize()

    async def get_chat_session(self, user_id, partition):
        table_name = f"chat_sessions_{partition}"
        await self.ensure_pool_initialized()

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f"SELECT user_id, chatgpt FROM {table_name} WHERE user_id = %s", (user_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return {"user_id": row[0], "chatgpt": json.loads(row[1]) if row[1] else []}
                return None

    async def create_chat_session(self, user_id, partition):
        table_name = f"chat_sessions_{partition}"
        await self.ensure_pool_initialized()

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                chat_session = {"user_id": user_id, "chatgpt": []}
                await cursor.execute(
                    f"INSERT INTO {table_name} (user_id, chatgpt) VALUES (%s, %s)",
                    (user_id, json.dumps(chat_session["chatgpt"])),
                )
                await conn.commit()
                return chat_session

    async def update_chat_session(self, user_id, chatgpt, partition):
        table_name = f"chat_sessions_{partition}"
        await self.ensure_pool_initialized()

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f"UPDATE {table_name} SET chatgpt = %s WHERE user_id = %s",
                    (json.dumps(chatgpt), user_id),
                )
                await conn.commit()

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()


# 主类
class ChatMemoryDB:
    def __init__(self, db_config: dict, redis_config: dict):
        self.max_memory = 24
        self.num_partitions = 5  # 设置分区数量
        self.db_config = db_config
        self.redis_cache = RedisCache(redis_config)  # Use RedisCache for managing Redis operations
        self.log = structlog.stdlib.get_logger().bind(name="chat_memory")
        self.repo = ChatSessionRepository(
            db_config
        )  # Use ChatSessionRepository to handle database operations
        self._initialized = False

    def _get_partition(self, user_id):
        # 计算哈希值并返回分区号
        hash_value = int(hashlib.md5(str(user_id).encode()).hexdigest(), 16)
        return hash_value % self.num_partitions

    async def _initialize(self):
        self.log.info("Initialize ChatMemoryDB")
        await asyncio.gather(
            self.repo.create_database_if_not_exists(),
            self.repo.initialize(),
            self.redis_cache.initialize(),
            self.repo.create_tables(self.num_partitions),
        )
        self._initialized = await self._check_initialization_status()

    async def _check_initialization_status(self) -> bool:
        # Check if MySQL pool is initialized
        if self.repo.pool is None:
            return False

        # Check if Redis connection is healthy
        if not await self.redis_cache.is_healthy():
            return False

        return True

    async def is_initialized(self) -> bool:
        if self._initialized:
            return self._initialized
        else:
            return await self._check_initialization_status()

    async def _get_or_create_chat_session(self, user_id):
        partition = self._get_partition(user_id)
        chat_session = None
        redis_key = f"chat_session:{partition}:{user_id}"

        # 从 Redis 获取缓存会话
        cached_session = await self.redis_cache.get(redis_key)
        if cached_session:
            self.log.info("Successfully retrieved chat session from Redis")
            chat_session = json.loads(cached_session)

        if not chat_session:
            # 从数据库获取会话
            chat_session = await self.repo.get_chat_session(user_id, partition)
            if not chat_session:
                self.log.info(f"New User: {user_id}")
                chat_session = await self.repo.create_chat_session(user_id, partition)
            await self.redis_cache.set(redis_key, json.dumps(chat_session), expire=3600)

        return chat_session

    @ensure_initialized
    async def add_memory(self, user_id, message):
        chat_session = await self._get_or_create_chat_session(user_id)
        chat_session["chatgpt"].extend(message)
        if len(chat_session["chatgpt"]) > self.max_memory:
            chat_session["chatgpt"] = chat_session["chatgpt"][-self.max_memory :]

        await self._update_memory(user_id=user_id, chat_session=chat_session)

    @ensure_initialized
    async def get_memory(self, user_id):
        chat_session = await self._get_or_create_chat_session(user_id)
        return list(chat_session["chatgpt"])

    @ensure_initialized
    async def clear_memory(self, user_id):
        self.log.info("Clearing memory", user_id=user_id)
        chat_session = await self._get_or_create_chat_session(user_id)
        chat_session["chatgpt"] = []
        await self._update_memory(user_id=user_id, chat_session=chat_session)

    async def _update_memory(self, user_id, chat_session):
        partition = self._get_partition(user_id)
        redis_key = f"chat_session:{partition}:{user_id}"

        await self.repo.update_chat_session(user_id, chat_session["chatgpt"], partition)
        await self.redis_cache.set(redis_key, json.dumps(chat_session), expire=3600)

    async def close(self):
        await self.redis_cache.close()
        await self.repo.close()
