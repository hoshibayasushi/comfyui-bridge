# comfyui-bridge

Bridge API between OpenWebUI and ComfyUI using FastAPI.

## Overview

This project provides a simple API bridge that allows:

- Sending prompts from OpenWebUI (Pipe)
- Automatically enqueueing them to ComfyUI via API
- Editing workflow_api.json on the fly

## Usage

```bash
uvicorn bridge:app --host 0.0.0.0 --port 8000
```

## Article (Japanese)
Qiita article:
https://qiita.com/y_hoshiba/items/6de7c791dfea64955c9e
