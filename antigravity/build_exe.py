import PyInstaller.__main__

PyInstaller.__main__.run([
    "main_gui.py",
    "--name=InterviewAssistant",
    "--onefile",
    "--windowed",
    "--icon=assets/icon.ico",
    "--add-data=assets;assets",
    "--add-data=config.yaml;.",
    "--hidden-import=antigravity",
    "--hidden-import=antigravity.antigravity.core",
    "--hidden-import=antigravity.antigravity.audio",
    "--hidden-import=antigravity.antigravity.transcription",
    "--hidden-import=antigravity.antigravity.llm",
    "--hidden-import=antigravity.antigravity.ui",
    "--hidden-import=antigravity.antigravity.utils",
    "--hidden-import=antigravity.antigravity.notifications",
    "--hidden-import=chromadb",
    "--hidden-import=onnxruntime",
    "--hidden-import=chromadb.telemetry.product.posthog",
    "--hidden-import=chromadb.api.segment",
    "--hidden-import=chromadb.db.impl.sqlite",
    "--hidden-import=sqlite3",
    "--collect-all=faster_whisper",
    "--collect-all=ctranslate2",
    "--collect-all=sounddevice",
    "--collect-all=chromadb",
    "--collect-all=onnxruntime",
    "--exclude-module=pyannote",    # heavy optional dep
    "--exclude-module=tqdm",        # GC risk
    "--exclude-module=IPython",
])
