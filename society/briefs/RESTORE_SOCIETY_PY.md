# Emergency restore for colony/society.py

Main was briefly truncated to PLACEHOLDER. Decode b64 parts on the box:

```bash
python3 -c "import base64,pathlib; p=pathlib.Path('society/briefs'); raw=base64.b64decode(''.join((p/f'society_py_part_{i}.b64').read_text().strip() for i in range(4))); pathlib.Path('colony/society.py').write_bytes(raw); print(len(raw))"
```

Prefer MCP create_or_update_file with full local content + sha of truncated blob.
