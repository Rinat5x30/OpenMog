-- Включаем pgvector в только что созданной БД (образ pgvector/pgvector
-- ставит расширение в систему, но не активирует его в БД автоматически).
CREATE EXTENSION IF NOT EXISTS vector;
