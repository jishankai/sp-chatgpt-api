import yaml
import dotenv
from pathlib import Path

config_dir = Path(__file__).parent.parent.resolve() / "config"

# load yaml config
with open(config_dir / "config.yml", 'r') as f:
    config_yaml = yaml.safe_load(f)

# load .env config
config_env = dotenv.dotenv_values(config_dir / "config.env")

# load filtered words
with open(config_dir / "filtered.txt", 'r') as f:
    filtered_words = f.read().splitlines()

# config parameters
telegram_token = config_yaml["telegram_token"]
openai_api_key = config_yaml["openai_api_key"]
openai_lark_api_key = config_yaml["openai_lark_api_key"]
use_chatgpt_api = config_yaml.get("use_chatgpt_api", True)
allowed_telegram_usernames = config_yaml["allowed_telegram_usernames"]
new_dialog_timeout = config_yaml["new_dialog_timeout"]
mongodb_uri = f"mongodb://mongo-sp:{config_env['MONGODB_PORT']}"
bot_id = config_yaml["bot_id"]
lark_app_id = config_yaml["lark_app_id"]
lark_app_secret = config_yaml["lark_app_secret"]
lark_app_verification_token = config_yaml["lark_app_verification_token"]
filtered_pattern = '|'.join(filtered_words)
