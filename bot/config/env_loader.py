"""
config.env_loader - Load .env file into os.environ.
"""

import os


def load_env():
    """Load .env key=value pairs into os.environ (only if not already set)."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        # Try parent of parent (project root)
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
        )
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    # Force update so UI changes in .env are reflected on reload
                    os.environ[k.strip()] = v.strip().strip("'\"")
