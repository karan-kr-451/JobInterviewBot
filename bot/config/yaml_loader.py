"""
config.yaml_loader - Load configuration from YAML file.

Replaces env_loader.py with a more structured YAML-based config.
Falls back to .env for backward compatibility.
"""

import os
import yaml


_config_cache = None


def load_config():
    """
    Load configuration from config.yaml.
    Falls back to .env if config.yaml doesn't exist.
    Returns dict with all configuration values.
    """
    global _config_cache
    
    # Find config.yaml
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    
    if os.path.exists(config_path):
        # Load from YAML
        with open(config_path, 'r', encoding='utf-8') as f:
            _config_cache = yaml.safe_load(f) or {}
        
        # Set environment variables for backward compatibility
        _set_env_from_config(_config_cache)
        
        return _config_cache
    else:
        # Fallback to .env for backward compatibility
        return _load_from_env()


def _set_env_from_config(config):
    """Set environment variables from config dict (always overwrite so reloads work)."""
    # LLM settings
    if 'llm' in config:
        llm = config['llm']
        if 'backend' in llm and llm['backend']:
            os.environ['LLM_BACKEND'] = str(llm['backend'])
        if 'gemini_api_key' in llm and llm['gemini_api_key']:
            os.environ['GEMINI_API_KEY'] = str(llm['gemini_api_key'])
        if 'groq_api_key' in llm and llm['groq_api_key']:
            os.environ['GROQ_API_KEY'] = str(llm['groq_api_key'])

    # Audio settings
    if 'audio' in config:
        audio = config['audio']
        if 'device_index' in audio and audio['device_index'] is not None:
            os.environ['DEVICE_INDEX'] = str(audio['device_index'])

    # Telegram settings
    if 'telegram' in config:
        tg = config['telegram']
        if 'bot_token' in tg and tg['bot_token']:
            os.environ['TELEGRAM_BOT_TOKEN'] = str(tg['bot_token'])
        if 'chat_id' in tg and tg['chat_id']:
            os.environ['TELEGRAM_CHAT_ID'] = str(tg['chat_id'])


def _load_from_env():
    """Fallback: Load from .env file (backward compatibility)."""
    config = {
        'llm': {},
        'audio': {},
        'telegram': {},
        'job': {},
        'documents': {},
        'overlay': {}
    }
    
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    
                    # Map to config structure
                    if k == 'LLM_BACKEND':
                        config['llm']['backend'] = v
                    elif k == 'GEMINI_API_KEY':
                        config['llm']['gemini_api_key'] = v
                    elif k == 'GROQ_API_KEY':
                        config['llm']['groq_api_key'] = v
                    elif k == 'DEVICE_INDEX':
                        config['audio']['device_index'] = int(v) if v else None
                    elif k == 'TELEGRAM_BOT_TOKEN':
                        config['telegram']['bot_token'] = v
                    elif k == 'TELEGRAM_CHAT_ID':
                        config['telegram']['chat_id'] = v
                    
                    # Also set in environment
                    os.environ[k] = v
    
    return config


def save_config(config):
    """Save configuration to config.yaml."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    # Update environment variables
    _set_env_from_config(config)
    
    # Update cache
    global _config_cache
    _config_cache = config


def get_config():
    """Get cached configuration (loads if not cached)."""
    global _config_cache
    if _config_cache is None:
        return load_config()
    return _config_cache


def reload_config():
    """Force reload configuration from file."""
    global _config_cache
    _config_cache = None
    return load_config()


# Load config on module import
load_config()