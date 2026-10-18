"""ModelScope Gradio entry; private materials are provisioned separately."""
import os
from app.ui import build

demo=build()

if __name__=='__main__':
    demo.launch(server_name='0.0.0.0',server_port=int(os.environ.get('PORT','7860')),ssr_mode=False)
