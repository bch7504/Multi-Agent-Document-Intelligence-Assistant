# Database migrations

Sprint 2 introduces the first migration for the `documents` lifecycle table.

Run it from the repository root with:

```bash
alembic -c backend/alembic.ini upgrade head
```

The API container runs this command automatically before FastAPI starts.
