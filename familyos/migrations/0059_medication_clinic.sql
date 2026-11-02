-- Where a prescription came from: the clinic or hospital named on it, beside the doctor.
ALTER TABLE medications ADD COLUMN clinic TEXT CHECK (clinic IS NULL OR length(clinic) <= 160);
