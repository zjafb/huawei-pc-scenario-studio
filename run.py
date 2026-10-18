"""启动入口：python run.py。魔搭创空间要求监听 0.0.0.0:7860。"""
import os

from app.ui import build
from app.studio import studio_css,studio_js

if __name__ == "__main__":
    build().launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")),
                   css=studio_css(),js=studio_js(),footer_links=[])
