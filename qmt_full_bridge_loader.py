#coding:gbk
# Paste this loader into the existing Full-QMT quote strategy once.
# Stop and run that strategy again after updating the source file.
_bridge_path = r"D:\mycode\50qq\qmt_full_bridge_probe.py"
with open(_bridge_path, "rb") as _bridge_file:
    _bridge_source = _bridge_file.read()
exec(compile(_bridge_source, _bridge_path, "exec"), globals(), globals())
