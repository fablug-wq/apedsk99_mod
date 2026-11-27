#!/usr/bin/env python3
"""Minimal Arduino .ino preprocessor: concatenates the sketch tabs (main first, then
alphabetical, like the IDE), adds #include <Arduino.h> and forward prototypes for
top-level functions, and writes a buildable sketch folder (empty .ino + all.cpp).

usage: inobuild.py <sketch_dir> <out_dir>
"""
import os, re, sys

src, out = sys.argv[1], sys.argv[2]
name = os.path.basename(os.path.normpath(src))
files = sorted(f for f in os.listdir(src) if f.endswith('.ino'))
files.remove(name + '.ino')
files.insert(0, name + '.ino')

parts = []
for f in files:
    with open(os.path.join(src, f), encoding='latin-1') as fh:
        parts.append('#line 1 "%s"\n' % os.path.join(src, f) + fh.read() + '\n')
text = ''.join(parts)

defre = re.compile(r'^((?:unsigned\s+|signed\s+)?[A-Za-z_]\w*\s*\*?)\s+(\w+)\s*\(([^;{)]*)\)\s*\{', re.M)
protos, first = [], None
for m in defre.finditer(text):
    ret, fn, args = m.group(1).strip(), m.group(2), m.group(3)
    if ret in ('else', 'return', 'switch', 'if', 'while', 'for', 'case'):
        continue
    if re.search(r'^\s*inline[^\n]*\b%s\s*\(' % fn, text, re.M):
        continue                                    # already has its own declaration
    if first is None:
        first = m.start()
    protos.append('%s %s(%s);' % (ret, fn, ' '.join(args.split())))

head = text[:first]
tail = text[first:]
cpp = '#include <Arduino.h>\n' + head + '\n' + '\n'.join(protos) + '\n#line 1 "tail"\n' + tail

os.makedirs(out, exist_ok=True)
oname = os.path.basename(os.path.normpath(out))
with open(os.path.join(out, oname + '.ino'), 'w') as fh:
    fh.write('// generated, see all.cpp\n')
with open(os.path.join(out, 'all.cpp'), 'w', encoding='latin-1') as fh:
    fh.write(cpp)
print('\n'.join(protos), file=sys.stderr)
