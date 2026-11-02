-- Which model reads a household's notices and answers its questions, and the least private place it may ever go.
-- model_routing: {"extraction": <profile>, "ask": <profile>, "floor": "cloud" | "confidential" | "own"}. Empty means the deployment's default.
ALTER TABLE households ADD COLUMN model_routing JSONB NOT NULL DEFAULT '{}'::jsonb;
