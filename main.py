from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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",
)

completion = client.chat.completions.create(
    model="nvidia/llama-3.3-nemotron-super-49b-v1.5",
    messages=[
        {"role": "system", "content": "/think"},
        {"role": "user", "content": "How many 'r's are in 'strawberry'?"},
    ],
    temperature=0.6,
    top_p=0.95,
    max_tokens=65536,
    frequency_penalty=0,
    presence_penalty=0,
    stream=True,
)

for chunk in completion:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
