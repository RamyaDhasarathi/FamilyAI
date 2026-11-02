-- A photographed notice may be read by the household's own model, which
-- sees the picture itself, instead of the OCR on this machine. Off until a
-- guardian says, and offered only where a model is named.
ALTER TABLE households ADD COLUMN pictures_by_model BOOLEAN NOT NULL DEFAULT false;
