local key         = KEYS[1]
local capacity    = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now_sec     = tonumber(ARGV[3])

local data        = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens      = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens      = capacity
    last_refill = now_sec
end

local elapsed = now_sec - last_refill
local refill  = elapsed * refill_rate
tokens        = math.min(capacity, tokens + refill)

if tokens < 1 then
    local retry_after = math.ceil((1 - tokens) / refill_rate)
    return {0, 0, retry_after}
end

tokens = tokens - 1

redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now_sec)
redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) * 2)

return {1, math.floor(tokens), -1}