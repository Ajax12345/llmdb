import openai

client = openai.OpenAI(
  api_key="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"
)

completion = client.chat.completions.create(
  model="gpt-4o-mini",
  store=True,
  messages=[
    {"role": "user", "content": "write a haiku about ai"}
  ]
)

print(completion.choices[0].message)