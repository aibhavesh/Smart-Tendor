-- Pre-provisioned roles for the initial team — TEMPLATE.
--
-- Copy to `scripts/seed_role_assignments.sql` (gitignored), put your own
-- addresses in the VALUES list, and run it ONCE after `alembic upgrade head`
-- and before those people sign in. Real addresses stay out of git.
--
--   cp scripts/seed_role_assignments.example.sql scripts/seed_role_assignments.sql
--   docker compose exec -T postgres psql -U tender -d tender_intel \
--     < scripts/seed_role_assignments.sql
--
-- Each row decides the role the account is *born* with; the row is consumed on
-- first sign-in. `assigned_by` is NULL because nobody was signed in to assign
-- them — the same convention the bootstrap migration uses.
--
-- Idempotent: skips an address that is already listed, and skips one that
-- already has an account (the elevation list does not govern live users —
-- change those with PATCH /admin/users/{id}/role instead).
--
-- Do NOT list your SUPER_ADMIN here. That one is seeded by the bootstrap
-- migration from BOOTSTRAP_SUPER_ADMIN_EMAIL, which ./scripts/setup.ps1 sets.
--
-- Every address must also be admissible: on a domain in ALLOWED_EMAIL_DOMAINS,
-- or listed individually in ALLOWED_EMAIL_EXCEPTIONS. A row here does not admit
-- anyone on its own; it only decides the role once they are admitted.
--
-- Valid roles: EMPLOYEE, MANAGER, ADMIN, SUPER_ADMIN.

INSERT INTO role_assignments (
    id, email, role, assigned_by, assigned_at, consumed_at, consumed_user_id
)
SELECT gen_random_uuid(), v.email, v.role, NULL, now(), NULL, NULL
FROM (VALUES
    ('manager@example.com', 'MANAGER'),
    ('admin@example.com',   'ADMIN')
) AS v(email, role)
WHERE NOT EXISTS (
    SELECT 1 FROM role_assignments r WHERE lower(r.email) = v.email
)
AND NOT EXISTS (
    SELECT 1 FROM users u WHERE lower(u.email) = v.email
);

-- Confirm what landed.
SELECT email, role, consumed_at IS NOT NULL AS used
FROM role_assignments
ORDER BY role, email;
