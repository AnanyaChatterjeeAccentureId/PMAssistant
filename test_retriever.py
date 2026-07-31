from Services.RetrieverService import RetrieverService

retriever = RetrieverService()

results = retriever.search(
    "Who has Azure certification?"
)

print()

print("Search Results")

print("--------------------------------")

for item in results:

    print(item)

    print()