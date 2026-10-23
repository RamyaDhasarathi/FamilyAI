-- A plan has a shape. A trip and a week of meals are both "plan this", and
-- both come out as days, a list to buy and legwork to do; what differs is
-- what the model is told and what the page calls things. The shape names
-- that, so the console can say "Groceries to order" where it would have
-- said "Bookings to make".
ALTER TABLE plans ADD COLUMN shape TEXT NOT NULL DEFAULT 'trip'
    CHECK (shape IN ('trip', 'meals', 'other'));
