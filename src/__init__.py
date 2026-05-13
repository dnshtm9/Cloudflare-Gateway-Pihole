import os
import re
from sys import exit
from src.colorlog import logger

# Constants
PREFIX = "AdBlock-DNS-Filters"
CACHE_FILE = "cloudflare_cache.json"

# Read .env variables 
def dot_env(file_path=".env"):
    env_vars = {}
    if os.path.exists(file_path):
        with open(file_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    value = re.sub(r'^["\'<]*(.*?)["\'>]*$', r'\1', value)
                    env_vars[key] = value
    return env_vars

env_vars = dot_env()

# Load environment or .env variables
CF_API_TOKEN = os.getenv("CF_API_TOKEN") or env_vars.get("CF_API_TOKEN")
CF_IDENTIFIER = os.getenv("CF_IDENTIFIER") or env_vars.get("CF_IDENTIFIER")

# Credential Validation
def validate_credential(value, name):
    if not value:
        return False
    # Check for empty or common placeholder patterns
    if value.lower() in ["", "your " + name.lower() + " value", "changeme", "xxx", "replace_me"]:
        return False
    return True

if not validate_credential(CF_API_TOKEN, "CF_API_TOKEN") or \
   not validate_credential(CF_IDENTIFIER, "CF_IDENTIFIER"):
    logger.error("Missing or invalid Cloudflare credentials. Please check your .env file or environment variables.")
    exit(1)
       
# Compile regex patterns
ids_pattern = re.compile(r"\$([a-f0-9-]+)")
ip_pattern = re.compile(r"^\d{1,3}(\.\d{1,3}){3,4}$")
replace_pattern = re.compile(r"(^([0-9.]+|[0-9a-fA-F:.]+)\s+|^(\|\||@@\|\||\*\.|\*))")
domain_pattern = re.compile(
r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)(?:\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?))*$"
)

# Logging functions
def error(message):
    logger.error(message)
    exit(1)

def silent_error(message):
    logger.warning(message)

def info(message):
    logger.info(message)
