local key        = KEYS[1]
local limit      = tonumber(ARGV[1])
local window_sec = tonumber(ARGV[2])
local now_ms     = tonumber(ARGV[3])
local request_id = ARGV[4]

local window_ms  = window_sec * 1000
local cutoff     = now_ms - window_ms

redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)

local count = redis.call('ZCARD', key)

if count >= limit then
    local ttl = redis.call('PTTL', key)
    return {0, 0, ttl}
end

redis.call('ZADD', key, now_ms, request_id)
redis.call('EXPIRE', key, window_sec)
return {1, limit - count - 1, -1}