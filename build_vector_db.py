from Services.TeamService import TeamService
from Services.LeaveService import LeaveService
from Services.EmbeddingService import EmbeddingService
from Services.VectorDBService import VectorDBService

print("Loading services...")

team_service = TeamService()
leave_service = LeaveService()

embedding_service = EmbeddingService()
vector_db = VectorDBService()

# -----------------------------
# Read Team Members
# -----------------------------
print("Reading Team Members...")

team_df = team_service.get_dataframe()

for index, row in team_df.iterrows():

    text = " | ".join(
        f"{column}: {str(row[column]) if row[column] == row[column] else ''}"
        for column in team_df.columns
    )

    embedding = embedding_service.get_embedding(text)

    vector_db.add_document(
        embedding,
        {
            "type": "Team",
            "content": text
        }
    )

    print(f"Indexed Team Member {index + 1}/{len(team_df)}")

# -----------------------------
# Read Leave Plan
# -----------------------------
print("\nReading Leave Plan...")

leave_df = leave_service.get_dataframe()

for index, row in leave_df.iterrows():

    text = " | ".join(
        f"{column}: {str(row[column]) if row[column] == row[column] else ''}"
        for column in leave_df.columns
    )

    embedding = embedding_service.get_embedding(text)

    vector_db.add_document(
        embedding,
        {
            "type": "Leave",
            "content": text
        }
    )

    print(f"Indexed Leave Record {index + 1}/{len(leave_df)}")

# -----------------------------
# Save FAISS Index
# -----------------------------
print("\nSaving Vector Database...")

vector_db.save()

print("\n===================================")
print("Vector Database Created Successfully")
print("===================================")

print(f"Total Documents Indexed : {len(vector_db.metadata)}")