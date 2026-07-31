from Services.EmbeddingService import EmbeddingService
from Services.VectorDBService import VectorDBService


class RetrieverService:

    def __init__(self):

        print("Step 1 - Creating EmbeddingService")

        self.embedding_service = EmbeddingService()

        print("Step 2 - EmbeddingService Loaded")

        self.vector_db = VectorDBService()

        print("Step 3 - Loading Vector DB")

        self.vector_db.load()

        print("Step 4 - Retriever Ready")

   

    def search(self, question, top_k=7):

        embedding = self.embedding_service.get_embedding(question)

        results = self.vector_db.search(embedding, top_k)

        return results