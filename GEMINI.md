## Gemini Added Memories
- Database Standard: Foreign keys must be defined with the same name as the referenced table's field (e.g., `user_id` for `User.id`) and include appropriate constraints (e.g., `INTEGER NOT NULL REFERENCES "Table"(id) ON DELETE CASCADE`).
