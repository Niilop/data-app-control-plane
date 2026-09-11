# backend/core/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

# Initialize a single, centralized rate limiter instance.
# get_remote_address uses the IP address of the incoming request.
limiter = Limiter(key_func=get_remote_address)