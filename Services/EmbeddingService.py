from sentence_transformers import SentenceTransformer


class EmbeddingService:

    def __init__(self):

        print("Loading SentenceTransformer...")

        self.model = SentenceTransformer("all-MiniLM-L6-v2")

        print("SentenceTransformer Loaded")

    def get_embedding(self, text):

        embedding = self.model.encode(
            text,
            convert_to_numpy=True
        )

        return embedding