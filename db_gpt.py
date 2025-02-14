import openai, typing

#https://platform.openai.com/docs/overview
#https://github.com/intellectronica/text-clustering-embedding-vs-prompting/blob/main/text-clustering-embedding-vs-prompting.ipynb



CLIENT = openai.OpenAI(
  api_key="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"
)

def get_embedding(client, text:str) -> typing.List[float]:
    return client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        encoding_format="float"
    ).data[0].embedding

def completion_test():
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        store=True,
        messages=[
            {"role": "user", "content": "write a haiku about ai"}
        ]
    )


    print(completion.choices[0].message)

if __name__ == '__main__':
    print(get_embedding(CLIENT, "this is a test"))