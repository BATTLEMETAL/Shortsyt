with open('lol_agent/lol_momentum_analyzer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_block = [
    '# Kill text keywords and weights (English LoL client only)\n',
    'KILL_KEYWORDS: Dict[str, Tuple[int, str]] = {\n',
    '    "pentakill":     (100, "PENTAKILL"),\n',
    '    "penta kill":    (100, "PENTAKILL"),\n',
    '    "penta":         (90,  "PENTAKILL"),\n',
    '    "quadra kill":   (75,  "QUADRAKILL"),\n',
    '    "quadrakill":    (75,  "QUADRAKILL"),\n',
    '    "quadra":        (65,  "QUADRAKILL"),\n',
    '    "triple kill":   (55,  "TRIPLE KILL"),\n',
    '    "triple":        (50,  "TRIPLE KILL"),\n',
    '    "double kill":   (35,  "DOUBLE KILL"),\n',
    '    "double":        (30,  "DOUBLE KILL"),\n',
    '    "killing spree": (20,  "KILLING SPREE"),\n',
    '    "slaughter":     (25,  "KILLING SPREE"),\n',
    '    "dominating":    (30,  "UNSTOPPABLE"),\n',
    '    "unstoppable":   (40,  "UNSTOPPABLE"),\n',
    '    "legendary":     (50,  "LEGENDARY"),\n',
    '    "godlike":       (60,  "GODLIKE"),\n',
    '}\n',
]

# Replace lines 46-79 (0-indexed: 45-78)
new_lines = lines[:45] + new_block + lines[79:]

with open('lol_agent/lol_momentum_analyzer.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print(f'OK - Polish keywords removed. Lines: {len(lines)} -> {len(new_lines)}')
