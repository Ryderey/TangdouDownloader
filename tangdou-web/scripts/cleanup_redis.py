#!/usr/bin/env python3
"""
清理 Redis 中 tangdou 相关的键
"""
import redis
import os

# Redis 连接配置
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)

def main():
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True
        )
        
        # 查找所有 tangdou 相关的键
        keys = r.keys('tangdou:*')
        print(f"Found {len(keys)} keys to delete")
        
        if keys:
            deleted = r.delete(*keys)
            print(f"Cleaned up {deleted} tangdou keys")
        else:
            print("No tangdou keys found")
            
    except Exception as e:
        print(f"Error cleaning Redis: {e}")

if __name__ == "__main__":
    main()