import os
import re
import sys

# Descriptive replacements
replacements = [
    (r'[WARN]', '[WARN]'),
    (r'[OK]', '[OK]'),
    (r'[OK]', '[OK]'),
    (r'[WAIT]', '[WAIT]'),
    (r'[LISTEN]', '[LISTEN]'),
    (r'[REC]', '[REC]'),
    (r'[PAUSE]', '[PAUSE]'),
    (r'[START]', '[START]'),
    (r'[SEARCH]', '[SEARCH]'),
    (r'--', '--'),
    (r'-', '-'),
    (r'->', '->'),
    (r'[FAIL]', '[FAIL]'),
    (r'-', '-'),
    (r'[!]', '[!]'),
    (r'[NEW]', '[NEW]'),
    (r'[HOT]', '[HOT]'),
    (r'[SAFE]', '[SAFE]'),
    (r'[TARGET]', '[TARGET]'),
    (r'[LOG]', '[LOG]'),
]

def clean_content(content):
    new_content = content
    for pattern, replacement in replacements:
        new_content = re.sub(pattern, replacement, new_content)
    
    # Strip any remaining non-ASCII characters
    ascii_content = []
    for c in new_content:
        if ord(c) < 128:
            ascii_content.append(c)
        else:
            # Replace unknown unicode with a space or a marker
            ascii_content.append(' ')
    
    return "".join(ascii_content)

def clean_file(file_path):
    try:
        # Read with utf-8, ignore errors to get what we can
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        new_content = clean_content(content)
        
        # Always write back as ASCII
        with open(file_path, 'w', encoding='ascii') as f:
            f.write(new_content)
        return True
    except Exception as e:
        print(f"Error cleaning {file_path}: {e}")
        return False

if __name__ == "__main__":
    root_dir = r'd:\InterviewBot\bot'
    print(f"Scanning {root_dir}...")
    count = 0
    for root, dirs, files in os.walk(root_dir):
        if '.venv' in root:
            continue
        for file in files:
            if file.endswith('.py') or file.endswith('.txt') or file.endswith('.log'):
                full_path = os.path.join(root, file)
                if clean_file(full_path):
                    count += 1
                    if count % 10 == 0:
                        print(f"Cleaned {count} files...")
    print(f"Done. Cleaned {count} files.")
