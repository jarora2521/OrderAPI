p = "data/wal.log"
text = open(p, "r", encoding="utf8").read()
# replace literal backslash-n with real newline (simple)
text = text.replace("\\n", "\n")
# also strip any leading BOM
text = text.lstrip("\ufeff")
open(p, "w", encoding="utf8").write(text)
print("WAL normalized (pass 2).")
