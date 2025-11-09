try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import os
from langchain.chat_models import init_chat_model

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

# model = init_chat_model(
#     # model="nvidia/llama-3.3-nemotron-super-49b-v1.5",
#     model="nvidia/llama-3.1-nemotron-ultra-253b-v1",
#     model_provider="openai",
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key=NVIDIA_API_KEY,
# )
model = None
