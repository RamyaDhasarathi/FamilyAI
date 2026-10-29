-- Two more things a guardian can hand to someone narrowly: medicine reminders, and the emergency card.
ALTER TABLE grants DROP CONSTRAINT grants_actions_check;
ALTER TABLE grants ADD CONSTRAINT grants_actions_check
    CHECK (cardinality(actions) > 0 AND actions <@ ARRAY['sign', 'pay', 'attend', 'submit', 'prepare', 'note', 'medication', 'emergency']::TEXT[]);
