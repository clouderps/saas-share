from . import models
from .models.redis_session import install_session_store

# Runs once per process when the module is imported; listing the module in
# server_wide_modules makes that happen before the first request.
install_session_store()
