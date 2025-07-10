cd .devcontainer && docker-compose up db pgadmin

docker exec -it devcontainer-db-1 psql -U postgres -d agentfusion -f /docker-entrypoint-initdb.d/progresdb.sql