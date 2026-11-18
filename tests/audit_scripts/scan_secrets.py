import os
import re

SUSPICIOUS = [
    re.compile(r'bot_token\s*=\s*[\'"][^\'"]+[\'"]', re.I),
    re.compile(r'TOKEN\s*=\s*[\'"].{20,}[\'"]', re.I),
    re.compile(r'ghp_[A-Za-z0-9]{30,}'),
    re.compile(r'discordapp\.com/api/webhooks/[0-9]+/[A-Za-z0-9_\-]+'),
]

found = []
for root, dirs, files in os.walk('src'):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                for idx, line in enumerate(fp, 1):
                    # Ignore comment examples or config.py default placeholders
                    if "os.getenv" in line or "Config." in line or "#" in line[:idx]:
                        continue
                    for pat in SUSPICIOUS:
                        if pat.search(line):
                            found.append((p, idx, line.strip()[:60]))

if found:
    print(f"Found {len(found)} potential secrets:", found)
else:
    print("Zero hardcoded secrets found in src/!")
