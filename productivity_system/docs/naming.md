# Database naming

- Use plural `snake_case` table names, such as `employees` and `tasks`.
- Use `id` as the primary key (`BigAutoField` in Django).
- Name foreign-key columns `<related_table>_id`, such as `employee_id`.
- Use `_at` for timestamps and `_date` for dates.
- Prefix boolean fields with `is_`, such as `is_granted` and `is_at_desk`.
- Use PascalCase singular Django model names and set `db_table` explicitly.
