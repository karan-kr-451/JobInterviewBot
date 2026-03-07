"""
config.documents - Document and logging paths.
"""

# =============================================================================
# DOCUMENTS
# =============================================================================

import os

# Base path relative to the bot package
_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_FOLDER = os.path.join(_base, "interview_docs")
LOG_FILE    = os.path.join(_base, "..", "interview_log.txt")
