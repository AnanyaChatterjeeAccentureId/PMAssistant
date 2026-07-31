import faiss
import pickle
import numpy as np
import os


class VectorDBService:

    def __init__(self):

        self.dimension = 384

        self.index_path = "vector_db/index.faiss"
        self.metadata_path = "vector_db/metadata.pkl"

        self.index = faiss.IndexFlatL2(self.dimension)
        self.metadata = []

    def add_document(self, embedding, document):

        vector = np.array([embedding]).astype("float32")

        self.index.add(vector)

        self.metadata.append(document)

    def save(self):

        faiss.write_index(self.index, self.index_path)

        with open(self.metadata_path, "wb") as file:
            pickle.dump(self.metadata, file)

    def load(self):

        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)

        if os.path.exists(self.metadata_path):
            with open(self.metadata_path, "rb") as file:
                self.metadata = pickle.load(file)

    def search(self, embedding, top_k=3):

        vector = np.array([embedding]).astype("float32")

        distances, indices = self.index.search(vector, top_k)

        results = []

        for idx in indices[0]:

            if idx != -1:
                results.append(self.metadata[idx])

        return results