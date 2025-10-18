import io, sys
p = "data/wal.log"
text = open(p, "r", encoding="utf8").read()
# remove BOM if present and replace literal backslash-n sequences with real newlines
text = text.lstrip("\ufeff").replace("\\\\n", "\n")
open(p, "w", encoding="utf8").write(text)
print("WAL normalized.")
