from Services.EmbeddingService import EmbeddingService

embedding = EmbeddingService()

vector = embedding.get_embedding(
    "Rahul knows Azure and Kubernetes."
)

print(type(vector))
print(len(vector))
print(vector[:10])