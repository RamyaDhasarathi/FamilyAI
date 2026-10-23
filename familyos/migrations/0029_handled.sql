-- The other half of handing a notice over: saying it is dealt with.
--
-- Accepting a date means "this is real, remind me". It is not "I paid it".
-- A notice handed to Archana with "can you pay this?" needs a way for her to
-- answer "paid, ref 4471" that closes the loop for the person who asked --
-- including a notice with no dates on it at all, which otherwise could never
-- be closed once it carried somebody's name.
--
-- On the artifact, beside the assignment it answers. Who and when are facts
-- for the audit; the note is the family's words and stays here.
ALTER TABLE input_artifacts
    ADD COLUMN handled_at TIMESTAMPTZ,
    ADD COLUMN handled_by UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN handled_note TEXT CHECK (handled_note IS NULL OR length(handled_note) <= 500);
